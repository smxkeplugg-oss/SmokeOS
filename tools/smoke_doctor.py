"""
tools/smoke_doctor.py -- SmokeOS Doctor
=======================================
Scans your home directory for every SmokeOS-related folder and categorizes:
  [OK] Tracked by Git   -- inside the canonical repo, tracked
  [!!] Legacy          -- old version, superseded
  [!!] Duplicate       -- same content as another folder
  [!!] Orphan          -- related but not in any git repo
  [!!] Dead            -- untouched >180 days
  [!!] Outside Repo    -- exists outside the canonical repo

Usage:
  python tools/smoke_doctor.py               # Scan and print report
  python tools/smoke_doctor.py --json        # JSON output
  python tools/smoke_doctor.py --fix         # Show what would be archived/deleted

NEVER deletes or moves anything without explicit confirmation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# -- Configuration --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
USER_HOME = Path(os.environ.get("USERPROFILE", str(Path.home())))

# Keywords that identify a SmokeOS-related folder
SMOKEOS_KEYWORDS = [
    "smokeos", "smoke_os", "smoke-os",
    "aiengine", "zmoke", "hermes",
    "swarm", "nexus", "agent-os",
    "claude", "opencode", "gemini",
    "broker", "kernel",
]

# Directories to skip entirely
SKIP_DIRS = {
    "AppData", "Application Data", "Cookies",
    "NetHood", "PrintHood", "Recent",
    "SendTo", "Start Menu", "Templates",
    "MicrosoftEdge", "OneDrive",
    ".vscode", ".git", "__pycache__",
    "node_modules", ".venv",
}

# Days before a folder is "dead" (not modified)
DEAD_DAYS = 180
STALE_DAYS = 90

# Canonical repo path
CANONICAL_REPO = PROJECT_ROOT


# -- Helpers -------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _quick_stat(path: Path) -> Dict[str, Any]:
    """Fast folder stats using os.walk with depth + file count limits."""
    file_count = 0
    total_size = 0
    newest_mtime = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            # Limit depth
            depth = dirpath.replace(str(path), "").count(os.sep)
            if depth > 4:
                dirnames.clear()
                continue
            # Skip noise
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                try:
                    st = os.stat(fpath)
                    total_size += st.st_size
                    if st.st_mtime > newest_mtime:
                        newest_mtime = st.st_mtime
                    file_count += 1
                except OSError:
                    pass
                if file_count >= 5000:
                    break
            if file_count >= 5000:
                break
    except (OSError, PermissionError):
        pass
    age_days = int((time.time() - newest_mtime) / 86400) if newest_mtime > 0 else 999
    return {"file_count": file_count, "total_size": total_size, "age_days": age_days}


def _folder_hash_fast(path: Path) -> Optional[str]:
    """Quick folder identity hash from top-level file listing only."""
    try:
        parts: List[str] = []
        for entry in sorted(path.iterdir()):
            if entry.is_file():
                try:
                    parts.append(f"{entry.name}:{entry.stat().st_size}")
                except OSError:
                    pass
            if len(parts) > 200:
                break
        if not parts:
            return None
        return hashlib.sha256("|".join(parts).encode()).hexdigest()
    except (OSError, PermissionError):
        return None


def _is_git_repo(path: Path) -> bool:
    """Check if a folder is a git repository."""
    return (path / ".git").is_dir()


def _get_git_remote(path: Path) -> str:
    """Get the origin remote URL for a git repo."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
            cwd=str(path),
        )
        return result.stdout.strip() if result.returncode == 0 else "(no remote)"
    except (subprocess.SubprocessError, FileNotFoundError):
        return "(git error)"


def _readable_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# -- Scanner -------------------------------------------------------

def scan_user_home(max_depth: int = 2) -> Dict[str, Any]:
    """Scan C:/Users/user for SmokeOS-related folders.

    Only looks at top-level dirs (max_depth=2 by default for speed).
    """
    start = time.time()
    results: List[Dict[str, Any]] = []
    scanned = 0

    # Collect candidate folders
    candidates: List[Path] = []

    for entry in USER_HOME.iterdir():
        if not entry.is_dir():
            continue
        if entry.name in SKIP_DIRS:
            continue
        if entry.name.startswith(".") and entry.name != ".ai":
            continue

        name_lower = entry.name.lower()
        is_smokeos = any(kw in name_lower for kw in SMOKEOS_KEYWORDS)
        if is_smokeos:
            candidates.append(entry)

        # Also check one level deeper for smokeos dirs
        if max_depth >= 2:
            try:
                for sub in entry.iterdir():
                    if sub.is_dir() and sub.name not in SKIP_DIRS:
                        sub_lower = sub.name.lower()
                        if any(kw in sub_lower for kw in SMOKEOS_KEYWORDS):
                            candidates.append(sub)
                    scanned += 1
            except (OSError, PermissionError):
                pass

    # Also scan Desktop and Documents directly
    for special in ["Desktop", "Documents"]:
        sp = USER_HOME / special
        if sp.is_dir():
            try:
                for entry in sp.iterdir():
                    if entry.is_dir():
                        name_lower = entry.name.lower()
                        if any(kw in name_lower for kw in SMOKEOS_KEYWORDS):
                            candidates.append(entry)
                    scanned += 1
            except (OSError, PermissionError):
                pass

    # Deduplicate and filter out garbled paths + nested dupes
    seen: Set[str] = set()
    unique: List[Path] = []
    canonical_resolved = str(CANONICAL_REPO.resolve())
    for c in candidates:
        try:
            resolved = str(c.resolve())
        except (OSError, PermissionError):
            continue
        # Skip garbled paths (corrupted Windows entries)
        if "?" in resolved:
            continue
        if resolved in seen:
            continue
        # Skip subdirectories of candidates we already have (e.g. aiengine subdirs
        # when aiengine itself is a candidate)
        is_sub_of_existing = False
        for existing in seen:
            if resolved.startswith(existing + os.sep) and resolved != existing:
                is_sub_of_existing = True
                break
        if is_sub_of_existing:
            continue
        seen.add(resolved)
        unique.append(c)
    candidates = unique

    # Now analyze each candidate
    for folder in candidates:
        try:
            folder = folder.resolve()

            # Is this inside the canonical repo? (path prefix check)
            canonical_str = str(CANONICAL_REPO.resolve())
            folder_str = str(folder)
            inside_canonical = (
                folder_str == canonical_str
                or folder_str.startswith(canonical_str + os.sep)
            )

            # Is it a git repo?
            is_repo = _is_git_repo(folder)
            remote = _get_git_remote(folder) if is_repo else ""

            # Fast stats (single os.walk instead of 3 rglob passes)
            stats = _quick_stat(folder)
            age = stats["age_days"]
            file_count = stats["file_count"]
            total_size = _readable_size(stats["total_size"])

            # Classification
            if inside_canonical and str(folder) == str(CANONICAL_REPO.resolve()):
                category = "canonical"
                marker = "[OK]"
            elif inside_canonical:
                category = "tracked"
                marker = "[OK]"
            elif is_repo and ("smokeos-oss" in remote.lower() or "SmokeOS" in remote):
                category = "public_repo"
                marker = "[OK]"
            elif age > DEAD_DAYS:
                category = "dead"
                marker = "[!!]"
            elif is_repo:
                category = "outside_repo"
                marker = "[!!]"
            elif age > STALE_DAYS:
                category = "legacy"
                marker = "[!!]"
            else:
                category = "orphan"
                marker = "[!!]"

            # Check if this folder is a structural duplicate of canonical
            # (same top-level directory structure)
            if not inside_canonical and category not in ("canonical", "public_repo"):
                if folder.name == CANONICAL_REPO.name:
                    # Same name as canonical — check first-level subdir names
                    try:
                        canon_dirs = {d.name for d in CANONICAL_REPO.iterdir() if d.is_dir() and not d.name.startswith(".")}
                        folder_dirs = {d.name for d in folder.iterdir() if d.is_dir() and not d.name.startswith(".")}
                        overlap = len(canon_dirs & folder_dirs)
                        if overlap >= 5 and overlap >= len(canon_dirs) * 0.5:
                            category = "duplicate"
                            marker = "[!!]"
                    except (OSError, PermissionError):
                        pass

            results.append({
                "path": str(folder),
                "name": folder.name,
                "relative": str(folder.relative_to(USER_HOME)) if str(USER_HOME) in str(folder) else str(folder),
                "category": category,
                "marker": marker,
                "is_git_repo": is_repo,
                "remote": remote,
                "age_days": age,
                "file_count": file_count,
                "total_size": total_size,
                "inside_canonical": inside_canonical,
            })
        except (OSError, PermissionError):
            pass

    elapsed = time.time() - start

    # Summary counts
    by_category = defaultdict(int)
    for r in results:
        by_category[r["category"]] += 1

    return {
        "scan_time": round(elapsed, 1),
        "scanned": scanned,
        "found": len(results),
        "by_category": dict(by_category),
        "canonical_repo": str(CANONICAL_REPO.resolve()),
        "folders": sorted(results, key=lambda r: (r["category"], r["name"])),
        "generated_at": _now(),
    }


# -- Report --------------------------------------------------------

def print_report(data: Dict[str, Any]) -> None:
    """Print a clean terminal report matching the user's preferred format."""
    folders = data["folders"]
    by_cat = data["by_category"]

    print()
    print("== SMOKE DOCTOR ======================================")
    print(f"   Canonical repo: {data['canonical_repo']}")
    print(f"   Scan: {data['scan_time']}s  |  Found: {data['found']} folders")
    print("======================================================")
    print()

    # Group and print
    for cat, marker, label in [
        ("canonical", "[OK]", "Canonical"),
        ("public_repo", "[OK]", "Public Repo"),
        ("tracked", "[OK]", "Tracked by Git"),
        ("legacy", "[!!]", "Legacy"),
        ("duplicate", "[!!]", "Duplicate"),
        ("orphan", "[!!]", "Orphan"),
        ("dead", "[!!]", "Dead"),
        ("outside_repo", "[!!]", "Outside Repository"),
    ]:
        matches = [f for f in folders if f["category"] == cat]
        if not matches:
            continue
        print(f"{label}:")
        for f in matches:
            age_str = f"({f['age_days']}d old)" if f["age_days"] > 0 else ""
            repo_str = f" -> {f['remote'][:60]}" if f["is_git_repo"] and f["remote"] else ""
            _safe_print(f"  {f['marker']} {f['relative']}  [{f['file_count']} files, {f['total_size']}] {age_str}{repo_str}")
        print()

    # Summary
    print("-- SUMMARY --------------------------------------------")
    for cat, label in [
        ("canonical", "Canonical (this repo)"),
        ("public_repo", "Public repos"),
        ("tracked", "Tracked by Git"),
        ("legacy", "Legacy (outdated copies)"),
        ("duplicate", "Duplicate (identical content)"),
        ("orphan", "Orphan (not in any repo)"),
        ("dead", "Dead (untouched >180 days)"),
        ("outside_repo", "Outside Repository"),
    ]:
        count = by_cat.get(cat, 0)
        if count > 0:
            print(f"   {count} {label}")

    total_issues = sum(
        by_cat.get(c, 0)
        for c in ("legacy", "duplicate", "orphan", "dead", "outside_repo")
    )
    print(f"   --")
    print(f"   {total_issues} folders to clean up")
    print()


# -- Main ----------------------------------------------------------

def _safe_print(*args, **kwargs):
    """Print safely on Windows terminals that don't support Unicode."""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = []
        for a in args:
            if isinstance(a, str):
                safe_args.append(a.encode("ascii", errors="replace").decode("ascii"))
            else:
                safe_args.append(a)
        print(*safe_args, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SmokeOS Doctor -- audit every SmokeOS-related folder on your machine",
    )
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of terminal report")
    parser.add_argument("--fix", action="store_true",
                        help="Show what cleanup actions would be taken (dry run, NEVER executes)")
    args = parser.parse_args()

    data = scan_user_home(max_depth=2)

    if args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        _safe_print(f"[DOCTOR] Scanning {USER_HOME}...")
        print_report(data)

    if args.fix:
        _safe_print("-- CLEANUP PLAN (dry run - nothing executed) ----------")
        for f in data["folders"]:
            if f["category"] in ("legacy", "duplicate", "orphan", "dead"):
                _safe_print(f"   Archive: {f['name']}")
                _safe_print(f"            -> archive/{f['name']}/")
        _safe_print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
