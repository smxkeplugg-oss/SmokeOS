"""
backend/core/env.py — Environment utility helpers
=================================================
Thin utility layer for common patterns that repeat across the codebase
but are NOT covered by ``backend.core.config.SmokeOSConfig`` (which owns
all typed config values like API keys, ports, and feature flags).

This module provides:
  - ``setup_windows_utf8()``  — the ``PYTHONUTF8=1`` fix repeated in 6 files.
  - ``is_truthy(value)``      — standard truthy-check used by 30+ settings.
  - ``get_device_name()``     — the ``COMPUTERNAME`` / ``HOSTNAME`` pattern.
  - ``load_dotenv()``         — idempotent ``.env`` loader.

These are convenience functions only.  For typed, validated config values
(API keys, ports, feature flags) use the ``cfg`` singleton from
``backend.core.config`` directly.

Usage::

    from backend.core.env import setup_windows_utf8, is_truthy
    setup_windows_utf8()
    if is_truthy(os.environ.get("SMOKEOS_OFFLINE")):
        ...

Author: FreeBuff Phase 1 consolidation
"""

from __future__ import annotations

import os
import sys


# ════════════════════════════════════════════════════════════════
# WINDOWS UTF-8 FIX
# ════════════════════════════════════════════════════════════════

def setup_windows_utf8() -> None:
    """Ensure stdout/stderr use UTF-8 encoding on Windows.

    Replaces the 6-copy pattern::

        if os.name == "nt":
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                os.environ["PYTHONUTF8"] = "1"

    Call this ONCE at the top of any entry-point script.
    Idempotent — calling twice is safe.
    """
    if os.name != "nt":
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        os.environ["PYTHONUTF8"] = "1"


# ════════════════════════════════════════════════════════════════
# TRUTHY / FALSY CHECK
# ════════════════════════════════════════════════════════════════

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY  = frozenset({"0", "false", "no", "off"})


def is_truthy(value: str | None) -> bool:
    """Return True if *value* is a truthy string (``1``, ``true``, ``yes``, ``on``).

    Returns False for ``None``, empty string, and any unrecognized value.

    Example::

        if is_truthy(os.environ.get("SMOKEOS_OFFLINE")):
            enable_offline_mode()
    """
    if value is None:
        return False
    return value.strip().lower() in _TRUTHY


def is_falsy(value: str | None) -> bool:
    """Return True if *value* is a falsy string (``0``, ``false``, ``no``, ``off``).

    Returns False for ``None``, empty string, and any unrecognized value.
    """
    if value is None:
        return False
    return value.strip().lower() in _FALSY


# ════════════════════════════════════════════════════════════════
# DEVICE IDENTITY
# ════════════════════════════════════════════════════════════════

def get_device_name(default: str = "SmokeStation") -> str:
    """Return the machine's hostname (cross-platform).

    Replaces the 4-copy pattern::

        os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "SmokeStation"))

    - Windows: ``COMPUTERNAME`` env var.
    - Other:   ``HOSTNAME`` env var → ``os.uname().nodename`` → *default*.
    """
    if os.name == "nt":
        return os.environ.get("COMPUTERNAME", default)
    return os.environ.get("HOSTNAME", _node_name(default))


def _node_name(default: str) -> str:
    """Return ``os.uname().nodename`` or *default* on failure."""
    try:
        return os.uname().nodename  # type: ignore[attr-defined]
    except AttributeError:
        import platform
        return platform.node() or default


# NOTE: ``.env`` loading is handled by ``backend.core.config._load_dotenv()``,
# which runs at import time.  Calling ``cfg.reload()`` from config.py re-reads
# ``.env`` without needing a separate loader here.  This avoids duplicating
# the loader logic across two modules.
