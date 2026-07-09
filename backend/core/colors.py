"""
backend/core/colors.py — ANSI terminal color constants
======================================================
Single source of truth for ANSI color codes used across the codebase.
Previously defined identically in start.py, process_watchdog.py,
smokeos_orchestrator.py, node_runner.py, smokeos_verify.py.

Usage::

    from backend.core.colors import GREEN, RED, YELLOW, RESET
    print(f"{GREEN}✓{RESET} Service started")

Design invariants:
  - Names are descriptive aliases over the ANSI escape sequences.
  - Every color has a single-character shortcut (G, R, Y, ...) AND a
    long descriptive name (GREEN, RED, YELLOW, ...).
  - ``no_color()`` returns True when NO_COLOR is set (respects
    https://no-color.org) or stdout is not a TTY.

Author: FreeBuff Phase 1 consolidation
"""

from __future__ import annotations

import os
import re
import sys

# ── Raw ANSI codes ──────────────────────────────────────────────

RED          = "\033[91m"
GREEN        = "\033[92m"
YELLOW       = "\033[93m"
BLUE         = "\033[94m"
MAGENTA      = "\033[95m"
CYAN         = "\033[96m"
WHITE        = "\033[97m"
DIM          = "\033[2m"
BOLD         = "\033[1m"
UNDERLINE    = "\033[4m"
RESET        = "\033[0m"

# ── Short aliases (matching existing convention) ─────────────────

R = RED
G = GREEN
Y = YELLOW
B = BLUE
M = MAGENTA
C = CYAN
W = WHITE

# ── Semantic aliases ────────────────────────────────────────────

OK = GREEN       # success checkmarks
WARN = YELLOW    # warnings
ERR = RED        # errors
INFO = CYAN      # informational messages
HIGHLIGHT = BOLD

# ── NO_COLOR support ────────────────────────────────────────────

def no_color() -> bool:
    """Return True if colors should be suppressed.

    Respects the NO_COLOR standard (https://no-color.org) and
    automatically disables colors when stdout is piped/redirected.
    """
    if os.environ.get("NO_COLOR", "").strip():
        return True
    if not sys.stdout.isatty():
        return True
    return False


def maybe_color(color: str, text: str) -> str:
    """Wrap *text* in *color* only when colors are enabled.

    Example::

        print(maybe_color(GREEN, "✓ Service started"))
    """
    if no_color():
        return text
    return f"{color}{text}{RESET}"


def strip_color(text: str) -> str:
    """Remove all ANSI escape sequences from *text*.

    Useful when writing colored output to a log file.
    """
    return re.sub(r"\033\[[0-9;]*m", "", text)
