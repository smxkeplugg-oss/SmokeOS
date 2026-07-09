#!/usr/bin/env python3
"""
backend/core/process_supervisor.py — Central supervised-process registry

Replaces 26+ scattered `subprocess.Popen(...)` call sites with a uniform
supervised-proc wrapper that gives operators a single dashboard widget
(`/dashboard/supervised`) showing everything aiengine has ever spawned.

Concurrent safety:
  - _REGISTRY    guarded by _REGISTRY_LOCK (snapshot-then-iterate)
  - _DEATH_SUBSCRIBERS guarded by _SUBSCRIBERS_LOCK (defensive, even
    though Python list.append/iteration is usually safe for short lists;
    protects against concurrent subscribe from a death-time callback)
  - kill_all()   uses a re-check loop so procs registered mid-shutdown
    from a death subscriber are still caught

Public API:
  SupervisedProcess      — object wrapping subprocess.Popen + bookkeeping
  supervise(name, cmd)   — factory: construct + start + register
  get_supervised(name)   — registry lookup
  list_supervised()      — current registry snapshot as dicts
  kill_all(wait_sec)     — kill every currently registered supervised proc
  subscribe_on_death(cb) — register callback invoked with death event dict
  unsubscribe_on_death(callback) — unregister
  death_log(limit)       — last N death events (newest last)

SupervisedProcess attributes:
  .pid, .port, .is_alive(), .exit_code, .lifetime_sec, .port_alive(), .to_dict()
  .kill() — uses system_utils.kill_process_tree() (cross-platform)

Subscriber contract:
  On death (_mark_dead), every registered subscriber is invoked with a dict:
    {"name", "pid", "exit_code", "port", "ts", "lifetime_sec"}
  Subscribers MUST NOT raise (exceptions are swallowed) so a buggy
  subscriber can never block subsequent subscribers.
"""

import subprocess
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from backend.core.system_utils import kill_process_tree, check_port


_SUBSCRIBERS_LOCK = threading.Lock()
_DEATH_SUBSCRIBERS: List[Callable[[dict], None]] = []

_REGISTRY_LOCK = threading.Lock()
_REGISTRY: Dict[str, "SupervisedProcess"] = {}

_DEATH_LOG: deque = deque(maxlen=200)


# ── SupervisedProcess ──────────────────────────────────────
class SupervisedProcess:
    """Wraps subprocess.Popen with consistent bookkeeping + ops visibility."""

    __slots__ = (
        "name", "_cmd", "_cwd", "_env", "port", "_proc", "_started_at",
        "_log_path", "_log_handle", "_creationflags", "capture_output", "tags",
        "_text", "_encoding", "_errors", "_shell",
    )

    def __init__(
        self,
        name: str,
        cmd,
        *,
        cwd: Optional[Path] = None,
        env: Optional[dict] = None,
        port: Optional[int] = None,
        log_path: Optional[Path] = None,
        capture_output: bool = True,
        creationflags: int = 0,
        tags: Optional[List[str]] = None,
        text: bool = False,
        encoding: Optional[str] = None,
        errors: Optional[str] = None,
        shell: Optional[bool] = None,
    ):
        self.name = name
        self._cmd = cmd
        self._cwd = str(cwd) if cwd else None
        self._env = env
        self.port = port
        self._proc: Optional[subprocess.Popen] = None
        self._started_at: Optional[datetime] = None
        self._log_path = log_path
        self._log_handle = None
        self._creationflags = creationflags
        self.capture_output = capture_output
        self.tags = list(tags or [])
        self._text = text
        self._encoding = encoding
        self._errors = errors
        self._shell = shell

    # ── lifecycle ───────────────────────────────────────────
    def start(self) -> "SupervisedProcess":
        """Spawn the subprocess. Registers globally. Idempotent."""
        if self._proc is not None:
            return self
        kwargs: dict = {}
        if self._cwd:
            kwargs["cwd"] = self._cwd
        if self._env:
            kwargs["env"] = self._env
        if self._creationflags:
            kwargs["creationflags"] = self._creationflags

        if self._log_path is not None:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = open(self._log_path, "ab")
            kwargs["stdout"] = self._log_handle
            kwargs["stderr"] = subprocess.STDOUT
        elif self.capture_output:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.STDOUT

        if self._text:
            kwargs["text"] = True
        if self._encoding:
            kwargs["encoding"] = self._encoding
        if self._errors:
            kwargs["errors"] = self._errors

        if self._shell is not None:
            kwargs["shell"] = self._shell
        elif not isinstance(self._cmd, list):
            kwargs["shell"] = True

        self._proc = subprocess.Popen(self._cmd, **kwargs)

        self._started_at = datetime.now()
        with _REGISTRY_LOCK:
            _REGISTRY[self.name] = self
        return self

    def kill(self) -> None:
        """Stop the proc via cross-platform taskkill/term+kill."""
        if self._proc and self._proc.poll() is None:
            try:
                kill_process_tree(self._proc)
            except Exception:
                pass
        # Close log handle if we opened one
        if self._log_handle:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None
        self._mark_dead()

    def is_alive(self) -> bool:
        """Function 'is_alive'."""
        if self._proc is None:
            return False
        return self._proc.poll() is None

    # ── accessors ───────────────────────────────────────────
    @property
    def pid(self) -> Optional[int]:
        """Function 'pid'."""
        return self._proc.pid if self._proc else None

    @property
    def exit_code(self) -> Optional[int]:
        """Function 'exit_code'."""
        if self._proc is None:
            return None
        return self._proc.poll()

    @property
    def lifetime_sec(self) -> Optional[float]:
        """Function 'lifetime_sec'."""
        if not self._started_at:
            return None
        return (datetime.now() - self._started_at).total_seconds()

    def port_alive(self) -> Optional[bool]:
        """True if port is bound, False if not, None if no port is configured."""
        if not self.port:
            return None
        try:
            return check_port(self.port, timeout=0.3)
        except Exception:
            return None

    def to_dict(self) -> dict:
        """Function 'to_dict'."""
        return {
            "name": self.name,
            "pid": self.pid,
            "port": self.port,
            "port_alive": self.port_alive(),
            "is_alive": self.is_alive(),
            "exit_code": self.exit_code,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "lifetime_sec": round(self.lifetime_sec or 0.0, 1),
            "cmd": " ".join(str(x) for x in self._cmd) if isinstance(self._cmd, list) else str(self._cmd),
            "cwd": self._cwd,
            "tags": list(self.tags),
        }

    # ── internal ────────────────────────────────────────────
    def _mark_dead(self) -> None:
        ev = {
            "name": self.name,
            "pid": self.pid,
            "exit_code": self.exit_code,
            "port": self.port,
            "ts": datetime.now().isoformat(),
            "lifetime_sec": round(self.lifetime_sec or 0.0, 1),
        }
        _DEATH_LOG.append(ev)
        # Snapshot subscribers under lock to avoid RuntimeError on
        # concurrent subscribe/unsubscribe during iteration.
        with _SUBSCRIBERS_LOCK:
            snapshot = list(_DEATH_SUBSCRIBERS)
        for cb in snapshot:
            try:
                cb(ev)
            except Exception:
                pass  # never let one buggy subscriber block others
        # Always remove from registry on death
        with _REGISTRY_LOCK:
            if self.name in _REGISTRY and _REGISTRY[self.name] is self:
                del _REGISTRY[self.name]


# ── Subscriber API ─────────────────────────────────────────
def subscribe_on_death(callback: Callable[[dict], None]) -> Callable:
    """Register a callback invoked with a dict when a supervised proc dies."""
    with _SUBSCRIBERS_LOCK:
        _DEATH_SUBSCRIBERS.append(callback)
    return callback


def unsubscribe_on_death(callback: Callable[[dict], None]) -> None:
    """Remove a callback. Silent no-op if it wasn't subscribed."""
    with _SUBSCRIBERS_LOCK:
        if callback in _DEATH_SUBSCRIBERS:
            _DEATH_SUBSCRIBERS.remove(callback)


# ── Public helpers ─────────────────────────────────────────
def supervise(name: str, cmd, **kwargs) -> SupervisedProcess:
    """Construct + start + register a SupervisedProcess in one call."""
    sp = SupervisedProcess(name, cmd, **kwargs)
    sp.start()
    return sp


def get_supervised(name: str) -> Optional[SupervisedProcess]:
    """Function 'get_supervised'."""
    with _REGISTRY_LOCK:
        return _REGISTRY.get(name)


def list_supervised() -> List[dict]:
    """Function 'list_supervised'."""
    with _REGISTRY_LOCK:
        snapshot = [sp.to_dict() for sp in _REGISTRY.values()]
    return snapshot


def kill_all(wait_sec: float = 5.0) -> int:
    """Kill every currently registered supervised proc.

    Uses a re-check loop so any proc registered MID-shutdown (e.g. by a
    death-subscriber that re-supervises the chain) is also caught.

    CRITICAL: calls sp.kill() UNCONDITIONALLY (not guarded by is_alive())
    so that sp._mark_dead() ALWAYS runs and unregisters the proc. Without
    this, naturally-exiting procs (which have no background sweep thread
    to call _mark_dead for them) would remain in the registry forever and
    spin this while-loop indefinitely. The internal is_alive() check
    inside kill() prevents kill_process_tree from re-firing on dead procs.

    Returns the count of procs that were alive at the moment of kill.
    """
    killed = 0
    while True:
        with _REGISTRY_LOCK:
            snapshot = list(_REGISTRY.values())
        if not snapshot:
            break
        for sp in snapshot:
            try:
                was_alive = sp.is_alive()
                sp.kill()  # unconditional — see docstring
                if was_alive:
                    killed += 1
            except Exception:
                pass  # individual kill failures should not abort the loop
    return killed


def death_log(limit: int = 50) -> List[dict]:
    """Function 'death_log'."""
    return list(_DEATH_LOG)[-limit:]
