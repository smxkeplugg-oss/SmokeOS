"""
backend/core/json_io.py — Canonical JSON I/O helpers
====================================================
Single entry point for safe, BOM-aware JSON file reads and writes.

Replaces the legacy ``json.load(open(p, "r", encoding="utf-8"))`` pattern,
which silently breaks on Windows-authored JSON files (Notepad, VSCode, and
PowerShell ``ConvertTo-Json`` all prepend a UTF-8 BOM ``\\xef\\xbb\\xbf``),
and leaks the file handle because there is no ``with`` statement.

This module provides:
  - ``load_json(path, ...)``     — BOM-safe, deterministic handle close, opt-in fallbacks.
  - ``dump_json(path, data, ...)`` — consistent indent, opt-in atomic-rename
                                    mirroring the pattern used in
                                    ``aiengine/audit/compressor.py:emit_inventory``.

Usage::

    from backend.core.json_io import load_json, dump_json

    cfg = load_json("config/projects.json", default={})     # BOM-safe; raises on missing
    dump_json(path, payload, atomic=True)                   # atomic write; survives AV races

Design invariants:
  - ``load_json`` defaults to ``encoding="utf-8-sig"`` so a leading BOM is
    silently stripped (matches the Windows origin of SmokeOS config files).
  - ``load_json`` defaults to ``raise_on_missing=True`` / ``raise_on_decode_error=True``
    — callers opt into a ``default`` fallback explicitly, never by accident.
  - ``load_json`` uses a context manager so the file handle closes even on
    decode failure (legacy form leaked the open() handle to GC).
  - ``dump_json`` defaults to ``indent=2`` + ``ensure_ascii=False``
    (consistent diff-able JSON across the codebase).
  - ``dump_json`` ``atomic=True`` writes to ``<path>.tmp`` then
    ``os.replace()`` onto the final path, retrying once on AV races.

Author: SmokeOS Phase 2G consolidation
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Union


# Allow Path | str consistently across the API surface.
PathLike = Union[Path, str]


# ════════════════════════════════════════════════════════════════
# LOAD
# ════════════════════════════════════════════════════════════════

def load_json(
    path: PathLike,
    *,
    default: Any = None,
    raise_on_missing: bool = True,
    raise_on_decode_error: bool = True,
    encoding: str = "utf-8-sig",
) -> Any:
    """Load a JSON file with BOM-aware encoding.

    Replaces the legacy ``json.load(open(p, "r", encoding="utf-8"))`` form
    (notably ``backend/kernel.py:2826`` pre-Phase-2G). Behavioural
    differences vs. the legacy:

    - ``encoding="utf-8-sig"`` strips a leading BOM silently, so files
      written by Notepad / VSCode / PowerShell parse cleanly. To read
      strict no-BOM-stripping, pass ``encoding="utf-8"``.
    - Uses a context manager so the file handle is always closed
      (legacy leaked ``open()`` handles to GC).
    - Optional ``default`` + ``raise_on_*`` knobs let the caller opt
      into fallback semantics vs. propagate.

    Args:
        path: Path or string to the JSON file.
        default: Value returned when *raise_on_missing* or
            *raise_on_decode_error* is False and the file is missing
            or malformed.
        raise_on_missing: If True (default), missing files raise
            ``FileNotFoundError``. If False, *default* is returned.
        raise_on_decode_error: If True (default), malformed JSON
            re-raises ``json.JSONDecodeError``. If False, *default*
            is returned.
        encoding: Text encoding for the file. ``"utf-8-sig"`` strips a
            leading BOM. Pass ``"utf-8"`` for strict no-strip.

    Returns:
        Parsed JSON value (dict, list, str, int, float, bool, or None).

    Raises:
        FileNotFoundError: ``raise_on_missing`` is True and the file is
            not present. (``FileNotFoundError`` is an ``OSError``
            subclass, so existing ``except (json.JSONDecodeError,
            OSError)`` blocks catch it without modification.)
        json.JSONDecodeError: ``raise_on_decode_error`` is True and the
            file contains malformed JSON.
        OSError: Other I/O errors (permission denied, etc.).
    """
    p = Path(path) if isinstance(path, str) else path

    # Use is_file() rather than try/except FileNotFoundError so the
    # raise_on_missing path produces a precise error message for
    # operator log readability.
    if not p.is_file():
        if raise_on_missing:
            raise FileNotFoundError(f"load_json: file not found: {p}")
        return default

    try:
        with p.open("r", encoding=encoding) as f:
            return json.load(f)
    except json.JSONDecodeError:
        if raise_on_decode_error:
            raise
        return default


# ════════════════════════════════════════════════════════════════
# DUMP
# ════════════════════════════════════════════════════════════════

def dump_json(
    path: PathLike,
    data: Any,
    *,
    atomic: bool = False,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    ensure_parents: bool = True,
    encoding: str = "utf-8",
) -> Path:
    """Write JSON to a file with consistent indent + encoding.

    Replaces inline ``json.dump(data, f, `` patterns. Defaults match
    the canonical style: ``indent=2`` (diff-able), ``ensure_ascii=False``
    (preserves Unicode verbatim), ``ensure_parents=True`` (creates
    missing parent directories).

    Args:
        path: Destination path or string.
        data: JSON-serialisable value.
        atomic: If True, write to ``<path>.tmp`` then ``os.replace()``
            onto *path*, retrying once if AV software holds the ``.tmp``
            open. Mirrors the pattern in
            ``aiengine/audit/compressor.py:emit_inventory``.
        indent: ``json.dump`` indent argument. ``None`` → compact.
            ``2`` (default) → canonical diff-able style.
        ensure_ascii: ``json.dump`` ensure_ascii argument.
            ``False`` (default) preserves Unicode verbatim.
        ensure_parents: If True (default), create missing parent dirs.
        encoding: File encoding for the write. ``"utf-8"`` is the
            canonical choice for diffability.

    Returns:
        The final path (a ``pathlib.Path``).
    """
    p = Path(path) if isinstance(path, str) else path

    if ensure_parents and p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)

    def _do_dump(target: Path) -> None:
        with target.open("w", encoding=encoding) as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)

    if not atomic:
        _do_dump(p)
        return p

    # Atomic: write to <path>.tmp, then os.replace onto the final path.
    # Mirrors aiengine/audit/compressor.py:emit_inventory()'s AV-race retry.
    tmp = p.with_suffix((p.suffix or "") + ".tmp")
    _do_dump(tmp)
    try:
        os.replace(tmp, p)
    except OSError:
        # AV software held the .tmp open mid-write. Drop the .tmp,
        # rewrite, retry. One-shot — failure here bubbles up to caller.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        _do_dump(tmp)
        os.replace(tmp, p)
    return p
