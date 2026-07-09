"""
backend/core/signals.py — Shared OS signal handler setup
=========================================================
Single entry point for installing graceful-shutdown signal handlers.
Replaces 10 duplicate ``signal.signal(signal.SIGINT, ...)`` blocks
scattered across start.py, start_all.py,
unified_sync_daemon.py, and others.

Usage (sync / threaded)::

    from backend.core.signals import install_shutdown_handlers

    shutdown_event = threading.Event()

    def handle_shutdown(signum: int) -> None:
        print("Shutting down...")
        shutdown_event.set()

    install_shutdown_handlers(handle_shutdown)

Usage (async / asyncio)::

    from backend.core.signals import install_async_signal_handlers

    loop = asyncio.get_running_loop()
    server_holder: list[uvicorn.Server] = []
    stop_event = install_async_signal_handlers(loop, server_holder)

Design invariants:
  - Cross-platform: handles SIGINT + SIGTERM everywhere; SIGBREAK on Windows.
  - Never raises (signals not supported → silent no-op).
  - Idempotent per process (subsequent calls overwrite the handler safely).

Author: FreeBuff Phase 1 consolidation
"""

from __future__ import annotations

import os
import signal
import sys
import time
from typing import Callable, Optional

# Type alias for handler signatures.
SignalHandler = Callable[[int, Optional[object]], None]


def install_shutdown_handlers(
    handler: SignalHandler,
    *,
    signals: tuple = (signal.SIGINT, signal.SIGTERM),
) -> None:
    """Register *handler* for common shutdown signals.

    Installs *handler* for ``SIGINT``, ``SIGTERM``, and (on Windows)
    ``SIGBREAK``.  The handler is NOT installed for ``SIGKILL``
    (which cannot be caught).

    On platforms where a signal is not supported, the error is silently
    swallowed (e.g. ``SIGBREAK`` on Linux, ``SIGTERM`` via
    ``loop.add_signal_handler`` on Windows).

    Args:
        handler: A ``callable(signum, frame)`` that performs shutdown
                 actions (set an ``Event``, flip a flag, etc.).
        signals: Additional signals to catch beyond the defaults
                 ``(SIGINT, SIGTERM)``.

    Example::

        import threading
        shutdown_event = threading.Event()

        def on_shutdown(signum, frame):
            print(f"Got signal {signum}, draining...")
            shutdown_event.set()

        install_shutdown_handlers(on_shutdown)
    """
    for sig in signals:
        try:
            signal.signal(sig, handler)
        except (ValueError, OSError, RuntimeError):
            # Signal not available on this platform / env (e.g. SIGTERM
            # inside a thread, or SIGKILL on purpose).
            pass

    # Windows-only: SIGBREAK = console close / taskkill / CTRL_BREAK_EVENT.
    if os.name == "nt" and hasattr(signal, "SIGBREAK"):
        try:
            signal.signal(signal.SIGBREAK, handler)
        except (ValueError, OSError, RuntimeError):
            pass


# ════════════════════════════════════════════════════════════════
# ASYNC (asyncio) SIGNAL HANDLERS
# ════════════════════════════════════════════════════════════════

def install_async_signal_handlers(
    loop: "asyncio.AbstractEventLoop",
    server_holder: list,
    *,
    print_message: bool = True,
) -> "asyncio.Event":
    """Install ``loop.add_signal_handler`` for graceful asyncio shutdown.

    Returns an ``asyncio.Event`` that callers can ``await`` to detect
    the shutdown signal.  Each server in *server_holder* has
    ``.should_exit = True`` set before the event is fired.

    Args:
        loop: The running event loop (``asyncio.get_running_loop()``).
        server_holder: A list of ``uvicorn.Server`` (or any object with a
                       ``should_exit`` attribute).
        print_message: If True, prints a drain message to stderr.

    Returns:
        ``asyncio.Event`` — set to True when SIGINT/SIGTERM is received.

    Example::

        loop = asyncio.get_running_loop()
        servers: list[uvicorn.Server] = []
        stop_event = install_async_signal_handlers(loop, servers)
        # ... launch servers ...
        await stop_event.wait()
    """
    import asyncio
    stop_event = asyncio.Event()

    def _trigger() -> None:
        if stop_event.is_set():
            return
        stop_event.set()
        for srv in server_holder:
            try:
                srv.should_exit = True
            except Exception:
                pass
        if print_message:
            print("\nsmokeos: SIGINT/SIGTERM — draining servers", flush=True)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _trigger)
        except (NotImplementedError, ValueError, RuntimeError):
            # loop.add_signal_handler unsupported (common on Windows
            # ProactorEventLoop).  Fall back to process-level signal.signal()
            # so that Ctrl+C still sets should_exit on ALL servers — without
            # this uvicorn's capture_signals() would clobber us.
            try:
                signal.signal(sig, lambda s, f, t=_trigger: t())
            except (ValueError, OSError, RuntimeError):
                pass

    return stop_event


# ════════════════════════════════════════════════════════════════
# CONVENIENCE: SELF-CONTAINED SHUTDOWN GUARD
# ════════════════════════════════════════════════════════════════

class ShutdownGuard:
    """Simple boolean guard flipped by signal handlers.

    Use in synchronous polling loops::

        guard = ShutdownGuard()
        install_shutdown_handlers(guard.signal_handler)

        while not guard.should_stop:
            do_work()
            guard.wait(interval=10)
    """

    def __init__(self) -> None:
        self.should_stop = False

    def signal_handler(self, signum: int, _frame: object | None = None) -> None:
        """Signal handler that sets should_stop = True."""
        if not self.should_stop:
            print(f"\n[shutdown] Received signal {signum}, stopping...", flush=True)
        self.should_stop = True

    def wait(self, interval: float = 1.0) -> None:
        """Sleep *interval* seconds, returning early if should_stop is set."""
        if self.should_stop:
            return
        deadline = time.time() + interval
        while time.time() < deadline and not self.should_stop:
            time.sleep(0.1)
