"""
backend/core/logging_config.py — Shared logging configuration
==============================================================
Single entry point for logging setup across SmokeOS.  Replaces 14
independent ``logging.basicConfig()`` calls scattered across the codebase.

Every script should call ``configure_logging(name, log_dir)`` ONCE near
its entry point.  Idempotent per logger name — calling twice is a no-op.

Usage::

    from backend.core.logging_config import configure_logging
    log = configure_logging("my_service", PROJECT_ROOT / "logs")
    log.info("ready")

The returned logger has:
  - A console (StreamHandler) with real-time INFO+ output.
  - A daily-rotating file handler at ``<log_dir>/<name>_<today>.log``
    (or ``<name>.log`` if ``daily_rotate=False``).

NEVER do this anymore::

    logging.basicConfig(level=logging.INFO, ...)
    logger = logging.getLogger(__name__)

Instead::

    from backend.core.logging_config import configure_logging
    log = configure_logging("my_service")

Author: FreeBuff Phase 1 consolidation
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from datetime import datetime


def configure_logging(
    name: str,
    log_dir: Optional[Path] = None,
    *,
    level: int = logging.INFO,
    fmt: str = "%(asctime)s %(levelname)s %(name)s | %(message)s",
    datefmt: str = "%H:%M:%S",
    daily_rotate: bool = True,
    console: bool = True,
    file_output: bool = True,
) -> logging.Logger:
    """Configure and return a named logger with console + file handlers.

    Args:
        name: Logger name (e.g. ``"my_service"``).  Also used as the
              log file basename unless *log_path* is provided.
        log_dir: Directory for log files.  Defaults to
                 ``PROJECT_ROOT / \"logs\"`` (auto-created).
        level: Log level (default ``logging.INFO``).
        fmt: Format string (see ``logging.Formatter``).
        datefmt: Date format string.
        daily_rotate: If True, writes to ``<name>_YYYY-MM-DD.log``.
                      If False, writes to ``<name>.log``.
        console: If True, add a ``StreamHandler(sys.stdout)``.
        file_output: If True, add a ``FileHandler``.

    Returns:
        The configured logger (also retrievable via
        ``logging.getLogger(name)``).

    Idempotent: calling again with the same *name* returns the
    existing logger without re-adding handlers.
    """
    logger = logging.getLogger(name)

    # Idempotency guard: if handlers are already attached, assume the
    # logger was configured earlier (by a previous call or by an imported
    # module).  No lock needed — ``logger.handlers`` is inherently per-logger.
    if logger.handlers:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(fmt, datefmt=datefmt)

    # ── Console handler ─────────────────────────────────────
    if console:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    # ── File handler ────────────────────────────────────────
    if file_output:
        if log_dir is None:
            log_dir = _default_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)

        if daily_rotate:
            today = datetime.now().strftime("%Y-%m-%d")
            log_path = log_dir / f"{name}_{today}.log"
        else:
            log_path = log_dir / f"{name}.log"

        fh = logging.FileHandler(str(log_path), mode="a", encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    logger.propagate = False
    return logger


def _default_log_dir() -> Path:
    """Return the default log directory (PROJECT_ROOT / "logs")."""
    return Path(__file__).resolve().parents[2] / "logs"


# ── Pre-configured root guard ───────────────────────────────────

def guard_root_handler() -> bool:
    """Return True if it is safe to configure the root logger.

    Use this in scripts that want to set up root-level logging but
    must not clobber handlers installed by imported modules.

    Returns True when ``logging.root`` has NO handlers attached,
    meaning ``basicConfig()`` can be called safely.

    Example::

        from backend.core.logging_config import guard_root_handler
        if guard_root_handler():
            logging.basicConfig(level=logging.INFO)
    """
    return not logging.root.handlers
