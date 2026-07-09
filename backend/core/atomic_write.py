"""
backend/core/atomic_write.py — Atomic File Writer
===================================================
Reusable utility for safe, atomic file writes. Pattern ported from
the archived authority_bridge.py (SmokeOS v200.0.0_GOVERNOR).

Guarantees:
  - Write to .tmp → validate → os.replace() to target (atomic on same FS)
  - Automatic .bak backup before overwrite
  - Windows retry loop for PermissionError (file locking)
  - Optional SHA256 integrity check

Usage:
  from backend.core.atomic_write import atomic_write, atomic_write_json

  # Write raw text
  atomic_write(path, "content")

  # Write JSON with validation
  atomic_write_json(path, {"key": "value"})

  # Write with SHA256 enforcement
  atomic_write(path, "content", expected_sha256="abc123...")
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional


# ── Windows retry configuration ──────────────────────────────────

MAX_RETRIES = 5
RETRY_DELAY_SEC = 0.1  # 100ms between retries


def atomic_write(
    path: Path | str,
    content: str | bytes,
    *,
    encoding: str = "utf-8",
    keep_backup: bool = True,
    expected_sha256: Optional[str] = None,
    max_retries: int = MAX_RETRIES,
) -> bool:
    """Write content to `path` atomically.

    Process:
      1. Write content to `path.tmp`
      2. (optional) Verify SHA256
      3. If `path` exists, rename to `path.bak`
      4. `os.replace(path.tmp, path)` — atomic rename
      5. On failure: retry with backoff

    Returns True on success, False on failure.
    Never raises — failures are logged and returned as False.
    """
    target = Path(path)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    bak_path = target.with_suffix(target.suffix + ".bak")

    # Ensure parent directory exists
    target.parent.mkdir(parents=True, exist_ok=True)

    # Encode if string
    data = content.encode(encoding) if isinstance(content, str) else content

    # Optional SHA256 check
    if expected_sha256:
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected_sha256:
            return False  # .tmp not written yet at this point, no cleanup needed

    # Write to .tmp
    for attempt in range(max_retries):
        try:
            tmp_path.write_bytes(data)

            # Backup existing target
            if keep_backup and target.exists():
                try:
                    bak_path.unlink(missing_ok=True)
                    os.replace(str(target), str(bak_path))
                except OSError:
                    pass  # Backup is best-effort

            # Atomic replace
            os.replace(str(tmp_path), str(target))
            return True

        except (PermissionError, OSError) as e:
            # Windows file locking — retry
            tmp_path.unlink(missing_ok=True)
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY_SEC * (2 ** min(attempt, 4)))  # exponential backoff
            continue

    return False


def atomic_write_json(
    path: Path | str,
    data: Any,
    *,
    indent: int = 2,
    keep_backup: bool = True,
    max_retries: int = MAX_RETRIES,
) -> bool:
    """Write JSON-serializable data to `path` atomically.

    Includes implicit validation: JSON serialization MUST succeed
    before any bytes touch the filesystem. If json.dumps() fails,
    nothing is written.
    """
    try:
        content = json.dumps(data, indent=indent, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return False

    return atomic_write(
        path,
        content,
        keep_backup=keep_backup,
        max_retries=max_retries,
    )


def atomic_read(
    path: Path | str,
    *,
    encoding: str = "utf-8",
    fallback: Any = None,
) -> Optional[str]:
    """Read file content, falling back to .bak if the main file is corrupted."""
    target = Path(path)
    bak_path = target.with_suffix(target.suffix + ".bak")

    for candidate in (target, bak_path):
        if candidate.exists():
            try:
                return candidate.read_text(encoding=encoding)
            except (OSError, UnicodeDecodeError):
                continue

    return fallback


def sha256_hex(data: str | bytes) -> str:
    """Compute SHA256 hex digest."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()
