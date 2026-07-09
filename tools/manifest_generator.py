#!/usr/bin/env python3
"""
manifest_generator.py — Auto-generate ai_manifest.json for SmokeOS.

Generates a machine-readable manifest that every AI session reads first,
eliminating the need to rediscover the project from scratch.

Usage:
    python tools/manifest_generator.py              # write ai_manifest.json
    python tools/manifest_generator.py --dry-run    # print to stdout only
    python tools/manifest_generator.py --check      # exit 0 if fresh, 1 if stale
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "ai_manifest.json"


# ── discovery helpers ────────────────────────────────────────────────

def _read_text(rel_path: str) -> str | None:
    p = PROJECT_ROOT / rel_path
    return p.read_text(encoding="utf-8") if p.exists() else None


def _find_test_dirs() -> list[str]:
    """Find all directories containing test files."""
    test_paths: set[str] = set()
    exclude_dirs = {".venv", "__pycache__", ".kilo", "node_modules", ".git", "archive"}
    for pattern in ["test_*.py", "*_test.py"]:
        for f in PROJECT_ROOT.rglob(pattern):
            if any(ex in f.parts for ex in exclude_dirs):
                continue
            test_paths.add(str(f.parent.relative_to(PROJECT_ROOT)).replace("\\", "/"))
    return sorted(test_paths)


def _count_tests() -> int:
    """Count test functions only (not classes, to avoid double-counting)."""
    count = 0
    exclude_dirs = {".venv", "__pycache__", ".kilo", "node_modules", ".git", "archive"}
    for f in PROJECT_ROOT.rglob("test_*.py"):
        if any(ex in f.parts for ex in exclude_dirs):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            count += len(re.findall(r"^\s*(?:async\s+)?def test_\w+", text, re.MULTILINE))
        except Exception:
            pass
    return count


# ── parsers ──────────────────────────────────────────────────────────

def _extract_version() -> str:
    config = _read_text("config.json")
    if config:
        try:
            return json.loads(config).get("version", "unknown")
        except json.JSONDecodeError:
            pass
    # fallback: git describe
    try:
        r = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=5,
        )
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _extract_git_commit() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=5,
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def _extract_ports() -> dict[str, int]:
    """Parse ARCHITECTURE.md for the port map."""
    arch = _read_text(".ai/ARCHITECTURE.md") or ""
    ports: dict[str, int] = {}
    in_table = False
    for line in arch.splitlines():
        if "| Port | Service" in line:
            in_table = True
            continue
        if in_table:
            if not line.strip().startswith("|"):
                break
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                try:
                    ports[parts[1]] = int(parts[0])
                except ValueError:
                    pass
    return ports


def _extract_pm2_services() -> list[str]:
    """Parse ecosystem.config.cjs for PM2 service names."""
    raw = _read_text("ecosystem.config.cjs") or ""
    names = re.findall(r'name:\s*"([^"]+)"', raw)
    return names


def _extract_directories() -> dict[str, list[str]]:
    """Categorize directories from DIRECTORY_RULES.md."""
    arch = _read_text(".ai/DIRECTORY_RULES.md") or ""
    result: dict[str, list[str]] = {"editable": [], "readonly": [], "caution": [], "forbidden": []}
    current_section: str | None = None

    section_patterns = {
        "editable": r"EDITABLE",
        "readonly": r"READ ONLY",
        "caution": r"CAUTION",
        "forbidden": r"FORBIDDEN",
    }

    for line in arch.splitlines():
        for key, pattern in section_patterns.items():
            if re.search(pattern, line, re.IGNORECASE):
                current_section = key
                break
        else:
            if current_section and line.strip().startswith("|") and "---" not in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if parts:
                    result[current_section].append(parts[0])

    return result


def _extract_architecture_dirs() -> list[str]:
    """Parse ARCHITECTURE.md for the directory map."""
    arch = _read_text(".ai/ARCHITECTURE.md") or ""
    dirs: list[str] = []
    in_section = False
    for line in arch.splitlines():
        if "Directory Map" in line:
            in_section = True
            continue
        if in_section:
            if line.strip().startswith("```"):
                if dirs:
                    break
                continue
            if line.strip().startswith("##") or line.strip().startswith("---"):
                break
            m = re.match(r"[-*]\s+`?([^`]+)`?", line.strip())
            if m:
                dir_name = m.group(1).split("/")[0].strip()
                if dir_name and dir_name not in dirs:
                    dirs.append(dir_name)
    return dirs


def _extract_entrypoints() -> list[str]:
    """Find all scripts with if __name__ == '__main__' in key dirs + root."""
    key_dirs = [".", "SmokeOS", "smokeos_local", "backend", "tools"]
    entrypoints: list[str] = []
    exclude_dirs = {".venv", "__pycache__", ".kilo", "node_modules", ".git", "archive"}
    for d in key_dirs:
        dp = PROJECT_ROOT / d if d != "." else PROJECT_ROOT
        if not dp.is_dir():
            continue
        for f in dp.rglob("*.py") if d != "." else dp.glob("*.py"):
            if any(ex in f.parts for ex in exclude_dirs):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                if 'if __name__ == "__main__"' in text or "if __name__ == '__main__'" in text:
                    entrypoints.append(str(f.relative_to(PROJECT_ROOT)).replace("\\", "/"))
            except Exception:
                pass
    return sorted(entrypoints)


def _extract_dependencies() -> list[str]:
    """Read key dependencies from ARCHITECTURE.md."""
    arch = _read_text(".ai/ARCHITECTURE.md") or ""
    deps: list[str] = []
    for line in arch.splitlines():
        m = re.match(r"[-*]\s+\*\*(.+?)\*\*:", line.strip())
        if m:
            deps.append(m.group(1))
    return deps


def _extract_active_agents() -> list[dict]:
    """Read active agents from the agent registry if available."""
    registry = _read_text("smokeos_local/core/agent_registry.json")
    if not registry:
        return []
    try:
        data = json.loads(registry)
        agents = []
        for agent_id, info in data.items():
            if isinstance(info, dict):
                agents.append({
                    "id": agent_id,
                    "status": info.get("status", "unknown"),
                    "type": info.get("type", "unknown"),
                })
        return agents
    except (json.JSONDecodeError, AttributeError):
        return []


def _extract_branch() -> str:
    try:
        r = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=5,
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


# ── architecture hash ────────────────────────────────────────────────

def _compute_architecture_hash() -> str:
    """SHA256 of all governance files + key entrypoints. Detects drift."""
    key_files = [
        ".ai/AI_RULES.md",
        ".ai/ARCHITECTURE.md",
        ".ai/DIRECTORY_RULES.md",
        ".ai/CODING_STANDARD.md",
        ".ai/ROADMAP.md",
        ".ai/DECISION_LOG.md",
        "ecosystem.config.cjs",
        "config.json",
    ]
    hasher = hashlib.sha256()
    for rel in sorted(key_files):
        p = PROJECT_ROOT / rel
        if p.exists():
            hasher.update(p.read_bytes())
    return hasher.hexdigest()[:16]


# ── main ─────────────────────────────────────────────────────────────

def generate() -> dict:
    """Generate the complete manifest."""
    return {
        "manifest_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "tools/manifest_generator.py",

        "project": {
            "name": "SmokeOS",
            "version": _extract_version(),
            "git_commit": _extract_git_commit(),
            "git_branch": _extract_branch(),
        },

        "architecture_hash": _compute_architecture_hash(),

        "ports": _extract_ports(),

        "services": {
            "pm2": _extract_pm2_services(),
        },

        "directories": {
            "main": _extract_architecture_dirs(),
            "governance": _extract_directories(),
        },

        "entrypoints": _extract_entrypoints(),

        "dependencies": _extract_dependencies(),

        "tests": {
            "directories": _find_test_dirs(),
            "count": _count_tests(),
        },

        "active_agents": _extract_active_agents(),

        "ai_entrypoints": [
            "AGENTS.md",
            "CLAUDE.md",
            "ai_manifest.json",
        ],
    }


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    check_mode = "--check" in sys.argv

    manifest = generate()

    if check_mode:
        existing = _read_text("ai_manifest.json")
        if existing:
            try:
                old = json.loads(existing)
                if old.get("architecture_hash") == manifest["architecture_hash"]:
                    print("[OK] Manifest is fresh.")
                    sys.exit(0)
            except json.JSONDecodeError:
                pass
        print("[STALE] Manifest is stale — run: python tools/manifest_generator.py")
        sys.exit(1)

    output = json.dumps(manifest, indent=2, ensure_ascii=False)

    if dry_run:
        print(output)
    else:
        MANIFEST_PATH.write_text(output + "\n", encoding="utf-8")
        print(f"[OK] ai_manifest.json written ({len(output)} bytes)")
        print(f"   Version: {manifest['project']['version']}")
        print(f"   Hash:    {manifest['architecture_hash']}")
        print(f"   Tests:   {manifest['tests']['count']}")
        print(f"   Ports:   {len(manifest['ports'])} defined")
        print(f"   Services: {len(manifest['services']['pm2'])} PM2")
        print(f"   Entries: {len(manifest['entrypoints'])} scripts")


if __name__ == "__main__":
    main()
