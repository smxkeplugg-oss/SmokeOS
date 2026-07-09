"""
tools/archaeologist.py — SmokeOS Archaeologist
===============================================
Scans the project and nearby directories for everything related to
SmokeOS. Finds duplicates, orphans, abandoned experiments, and builds
a dependency graph.

NEVER deletes or moves anything. Reports only.

Usage:
  python tools/archaeologist.py                 # Scan project dir (default)
  python tools/archaeologist.py --full          # Scan your home directory
  python tools/archaeologist.py --json          # JSON output only
  python tools/archaeologist.py --output report.md  # Write to file

Output files:
  archaeology_report.json   — machine-readable full report
  archaeology_report.md     — human-readable summary
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ── Configuration ──────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Keywords that signal a file is SmokeOS-related
SMOKEOS_KEYWORDS = [
    "smokeos", "smoke_os", "smoke-os",
    "hermes", "antigravity", "nzt-41", "nzt41",
    "claude_bridge", "gemini_executor", "zmoke",
    "swarm", "nexus", "autonomous_trader",
    "phone_gateway", "guardrails", "command_center",
    "swarm_chamber", "swarm_bus", "smokeos_local",
]

# Directories to always skip
SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "node_modules",
    ".mypy_cache", ".pytest_cache", ".tox", ".eggs",
    "dist", "build", ".vscode", ".idea",
}

# File extensions to scan for content
SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
    ".md", ".yml", ".yaml", ".toml", ".cfg", ".ini",
    ".cjs", ".mjs", ".bat", ".ps1", ".sh",
    ".html", ".css", ".env.example",
}

# Files considered "abandoned" if not modified in this many days
ABANDONED_DAYS = 180

# Files considered "stale" if not modified in this many days
STALE_DAYS = 90


# ── Helpers ───────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_file(path: Path) -> Optional[str]:
    """SHA-256 hash of file contents for duplicate detection."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, PermissionError):
        return None


def _extract_imports(py_path: Path) -> List[str]:
    """Extract Python import targets from a .py file."""
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return []
    imports: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    return imports


def _readable_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


# ── Core Scan ─────────────────────────────────────────────────────

def scan_directory(
    root: Path,
    max_depth: int = 5,
    max_files: int = 50_000,
) -> Dict[str, Any]:
    """Walk a directory tree and collect every file that matches
    SmokeOS keywords. Returns indexed results.

    Args:
        root: Directory to scan.
        max_depth: Maximum directory depth from root.
        max_files: Bail out after scanning this many files (safety limit).
    """
    start = time.time()
    root_depth = len(root.parts)
    scanned = 0
    hits: List[Dict[str, Any]] = []
    hit_paths: Set[str] = set()

    for dirpath, dirnames, filenames in os.walk(root):
        # Depth limit
        current_depth = len(Path(dirpath).parts) - root_depth
        if current_depth > max_depth:
            dirnames.clear()
            continue

        # Skip known noise directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for fname in filenames:
            if scanned >= max_files:
                break
            scanned += 1

            fpath = Path(dirpath) / fname
            ext = fpath.suffix.lower()

            # Only scan known extensions for content
            if ext not in SCAN_EXTENSIONS:
                continue

            # Check filename + content for keywords
            fname_lower = fname.lower()
            keyword_in_name = any(kw in fname_lower for kw in SMOKEOS_KEYWORDS)
            keyword_in_content = False

            if not keyword_in_name:
                # Only read content if name didn't match
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")[:4096]
                    content_lower = content.lower()
                    keyword_in_content = any(kw in content_lower for kw in SMOKEOS_KEYWORDS)
                except (OSError, PermissionError, UnicodeDecodeError):
                    pass

            if not keyword_in_name and not keyword_in_content:
                continue

            # Found a hit
            rel = str(fpath.relative_to(root))
            try:
                stat = fpath.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                size = stat.st_size
            except OSError:
                mtime = "unknown"
                size = 0

            age_days = 0
            if mtime != "unknown":
                try:
                    mtime_dt = datetime.fromisoformat(mtime)
                    age_days = (datetime.now(timezone.utc) - mtime_dt).days
                except ValueError:
                    pass

            status = "active"
            if age_days > ABANDONED_DAYS:
                status = "abandoned"
            elif age_days > STALE_DAYS:
                status = "stale"

            hits.append({
                "path": rel,
                "abs_path": str(fpath),
                "ext": ext,
                "size": size,
                "size_human": _readable_size(size),
                "mtime": mtime,
                "age_days": age_days,
                "status": status,
                "matched_keywords": [
                    kw for kw in SMOKEOS_KEYWORDS
                    if kw in fname_lower
                ],
            })
            hit_paths.add(str(fpath))

        if scanned >= max_files:
            break

    elapsed = time.time() - start
    return {
        "root": str(root),
        "scanned": scanned,
        "hits": len(hits),
        "elapsed_sec": round(elapsed, 1),
        "files": hits,
    }


# ── Analysis ──────────────────────────────────────────────────────

def analyze(
    scan_results: Dict[str, Any],
    git_tracked: Set[str],
) -> Dict[str, Any]:
    """Analyze scan results to find duplicates, orphans, and patterns.

    Args:
        scan_results: Output from scan_directory().
        git_tracked: Set of absolute paths tracked by git.
    """
    files = scan_results.get("files", [])
    project_root = PROJECT_ROOT

    # Classify each file
    in_git: List[Dict[str, Any]] = []
    orphans: List[Dict[str, Any]] = []
    outside_project: List[Dict[str, Any]] = []

    for f in files:
        abs_path = f["abs_path"]
        if abs_path in git_tracked:
            in_git.append(f)
        elif str(project_root) in abs_path:
            orphans.append(f)
        else:
            outside_project.append(f)

    # Duplicate detection by content hash
    hash_map: Dict[str, List[str]] = defaultdict(list)
    for f in files:
        path = Path(f["abs_path"])
        if path.suffix == ".py" and f["size"] < 100_000:
            h = _hash_file(path)
            if h:
                hash_map[h].append(f["path"])

    duplicates = {
        h: paths for h, paths in hash_map.items()
        if len(paths) > 1
    }

    # Abandoned experiments
    abandoned = [f for f in files if f["status"] == "abandoned"]
    stale = [f for f in files if f["status"] == "stale"]

    # By extension
    by_ext: Dict[str, int] = defaultdict(int)
    for f in files:
        by_ext[f["ext"]] += 1

    # By status
    by_status: Dict[str, int] = defaultdict(int)
    for f in files:
        by_status[f["status"]] += 1

    # Dependency graph (from Python imports in project files)
    imports: Dict[str, List[str]] = {}
    for f in files:
        path = Path(f["abs_path"])
        if path.suffix == ".py" and str(project_root) in str(path):
            try:
                deps = _extract_imports(path)
                rel = str(path.relative_to(project_root))
                imports[rel] = deps
            except Exception:
                pass

    # Find "critical" files — ones imported by many others
    imported_by: Dict[str, int] = defaultdict(int)
    for file_path, deps in imports.items():
        for dep in deps:
            imported_by[dep] += 1

    critical_files = sorted(
        [(mod, count) for mod, count in imported_by.items() if count >= 3],
        key=lambda x: -x[1],
    )

    # Orphan launchers: .bat, .ps1, .sh files not in git
    orphan_launchers = [
        f for f in orphans
        if f["ext"] in (".bat", ".ps1", ".sh")
    ]

    return {
        "summary": {
            "total_hits": len(files),
            "in_git": len(in_git),
            "orphans_in_project": len(orphans),
            "outside_project": len(outside_project),
            "duplicate_groups": len(duplicates),
            "abandoned": len(abandoned),
            "stale": len(stale),
            "by_extension": dict(by_ext),
            "by_status": dict(by_status),
            "critical_modules": critical_files[:20],
        },
        "duplicates": {
            f"group_{i}": paths
            for i, (h, paths) in enumerate(duplicates.items())
        },
        "orphans": orphans,
        "outside_project": outside_project[:50],  # cap for readability
        "abandoned_files": abandoned,
        "orphan_launchers": orphan_launchers,
        "imports": imports,
        "scan_config": {
            "project_root": str(PROJECT_ROOT),
            "keywords": SMOKEOS_KEYWORDS,
            "abandoned_days": ABANDONED_DAYS,
            "stale_days": STALE_DAYS,
        },
    }


# ── Report Generator ──────────────────────────────────────────────

def generate_report(analysis: Dict[str, Any]) -> str:
    """Generate a human-readable markdown report."""
    s = analysis["summary"]
    lines = [
        "# SmokeOS Archaeologist — Scan Report",
        f"**Generated**: {_now()}",
        f"**Project root**: `{PROJECT_ROOT}`",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total files matching SmokeOS keywords | {s['total_hits']} |",
        f"| Tracked in git | {s['in_git']} |",
        f"| Orphans (in project, not in git) | {s['orphans_in_project']} |",
        f"| Outside project | {s['outside_project']} |",
        f"| Duplicate content groups | {s['duplicate_groups']} |",
        f"| Abandoned (>180 days) | {s['abandoned']} |",
        f"| Stale (90-180 days) | {s['stale']} |",
        "",
        "## Status Breakdown",
        "",
    ]

    for status, count in sorted(s["by_status"].items()):
        lines.append(f"- **{status}**: {count} files")

    lines += [
        "",
        "## By Extension",
        "",
    ]
    for ext, count in sorted(s["by_extension"].items(), key=lambda x: -x[1])[:10]:
        lines.append(f"- `{ext}`: {count} files")

    # Critical modules
    if s["critical_modules"]:
        lines += [
            "",
            "## 🔗 Critical Modules (imported by 3+ files)",
            "",
        ]
        for mod, count in s["critical_modules"]:
            lines.append(f"- `{mod}` — imported by {count} files")

    # Duplicates
    if analysis["duplicates"]:
        lines += [
            "",
            "## ⚠️ Duplicate Files (identical content, different paths)",
            "",
        ]
        for group, paths in analysis["duplicates"].items():
            lines.append(f"**{group}**:")
            for p in paths:
                lines.append(f"  - `{p}`")
            lines.append("")

    # Orphan launchers
    if analysis["orphan_launchers"]:
        lines += [
            "",
            "## 🚀 Orphan Launch Scripts (not tracked in git)",
            "",
        ]
        for f in analysis["orphan_launchers"][:20]:
            lines.append(f"- `{f['path']}` ({f['size_human']}, last modified {f['mtime'][:10]})")

    # Abandoned files
    if analysis["abandoned_files"]:
        lines += [
            "",
            "## 🏚️ Abandoned Files (>180 days since last modified)",
            "",
        ]
        for f in sorted(analysis["abandoned_files"], key=lambda x: -x["age_days"])[:30]:
            lines.append(f"- `{f['path']}` — {f['age_days']} days old, {f['size_human']}")

    # Orphans (project files not in git)
    if analysis["orphans"]:
        lines += [
            "",
            "## 👻 Orphan Files (in project but not tracked by git)",
            "",
        ]
        for f in analysis["orphans"][:30]:
            lines.append(f"- `{f['path']}` ({f['size_human']}, {f['status']})")

    # Recommendations
    lines += [
        "",
        "## 💡 Recommendations",
        "",
    ]

    if s["orphans_in_project"] > 0:
        lines.append(f"- **{s['orphans_in_project']} orphan files** in the project directory are not tracked by git. Consider: `git add` (if they belong) or move to an archive directory.")
    if s["duplicate_groups"] > 0:
        lines.append(f"- **{s['duplicate_groups']} groups of duplicate files** found. Consolidate into single canonical copies.")
    if s["abandoned"] > 0:
        lines.append(f"- **{s['abandoned']} abandoned files** haven't been touched in over {ABANDONED_DAYS} days. Archive or delete after review.")
    if analysis["orphan_launchers"]:
        lines.append(f"- **{len(analysis['orphan_launchers'])} orphan launch scripts** found outside git. May be dead startup pathways.")

    lines += [
        "",
        "---",
        "*Generated by SmokeOS Archaeologist. This tool NEVER deletes or modifies files.*",
        f"*Run: `python tools/archaeologist.py`*",
    ]

    return "\n".join(lines)


# ── Git integration ───────────────────────────────────────────────

def get_git_tracked() -> Set[str]:
    """Return set of absolute paths for all git-tracked files."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "ls-files", "--full-name"],
            capture_output=True, text=True, timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            return set()
        return {
            str((PROJECT_ROOT / line.strip()).resolve())
            for line in result.stdout.splitlines()
            if line.strip()
        }
    except (subprocess.SubprocessError, FileNotFoundError):
        return set()


# ── Main ──────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SmokeOS Archaeologist — find every SmokeOS-related file on your system",
        epilog="NEVER deletes or modifies files. Reports only.",
    )
    parser.add_argument("--full", action="store_true",
                        help=f"Scan entire {PROJECT_ROOT} recursively (may be slow)")
    parser.add_argument("--depth", type=int, default=5,
                        help="Max directory depth (default: 5)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON only (no markdown report)")
    parser.add_argument("--output", type=str, default=None,
                        help="Write markdown report to file")
    args = parser.parse_args()

    scan_root = PROJECT_ROOT
    if args.full:
        scan_root = Path(os.environ.get("USERPROFILE", str(Path.home())))

    print(f"[ARCHAEOLOGIST] Scanning: {scan_root}")
    print(f"[ARCHAEOLOGIST] Keywords: {', '.join(SMOKEOS_KEYWORDS[:5])}...")
    print()

    # 1. Scan
    results = scan_directory(scan_root, max_depth=args.depth)

    # 2. Get git tracking info
    git_tracked = get_git_tracked()

    # 3. Analyze
    analysis = analyze(results, git_tracked)

    # 4. Generate report
    report = generate_report(analysis)

    # 5. Write outputs
    json_path = PROJECT_ROOT / "archaeology_report.json"
    md_path = PROJECT_ROOT / "archaeology_report.md"

    json_path.write_text(json.dumps(analysis, indent=2, default=str), encoding="utf-8")
    md_path.write_text(report, encoding="utf-8")

    print(f"[ARCHAEOLOGIST] Report written:")
    print(f"  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    print()
    print(f"[ARCHAEOLOGIST] Summary:")
    s = analysis["summary"]
    print(f"  {s['total_hits']} files found matching SmokeOS keywords")
    print(f"  {s['in_git']} tracked by git")
    print(f"  {s['orphans_in_project']} orphans (untracked)")
    print(f"  {s['duplicate_groups']} duplicate groups")
    print(f"  {s['abandoned']} abandoned (>180 days)")
    print(f"  {s['stale']} stale (90-180 days)")

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\n  Report also written to: {args.output}")

    if args.json:
        print(json.dumps(analysis, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
