#!/usr/bin/env python3
"""
backend/core/system_utils.py — Shared system utilities

Canonical implementations for:
  - check_port(port, timeout) → TCP liveness check (replaces per-script duplicates)
  - get_system_metrics(root)  → CPU/RAM/Disk metrics (no psutil dependency)
  - kill_process_tree(proc)   → Windows-safe + Linux-safe process tree termination

Extracted from start.py, smokeos_orchestrator.py, aiengine_cli.py, and
backend/core/process_watchdog.py so every script uses the same implementation.
Cross-platform (Windows + Linux).
"""

import os
import shutil
import socket
import subprocess
from pathlib import Path


# ══════════════════════════════════════════════════════════
# PORT LIVENESS CHECK
# ══════════════════════════════════════════════════════════
def check_port(port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is accepting connections on 127.0.0.1.

    Args:
        port: The TCP port number to check.
        timeout: Socket connect timeout in seconds (default 2.0).

    Returns:
        True if the port accepts a connection, False otherwise.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


# ══════════════════════════════════════════════════════════
# PROCESS TREE TERMINATION
# ══════════════════════════════════════════════════════════
def kill_process_tree(proc) -> None:
    """Kill a process and all its children.

    Args:
        proc: A subprocess.Popen-like object exposing .pid, .terminate(), .kill(),
              and .wait(timeout). Passing None is a safe no-op.

    Behavior:
      - Windows: uses `taskkill /T /F /PID <pid>` to terminate the tree.
      - Other OS: calls proc.terminate() then proc.wait(timeout=5); falls back
                  to proc.kill() if that fails.
    """
    if proc is None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                f"taskkill /T /F /PID {proc.pid}",
                shell=True, capture_output=True, timeout=5,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════
# SYSTEM METRICS (CPU / RAM / DISK)
# ══════════════════════════════════════════════════════════
def get_system_metrics(root: Path | None = None) -> dict:
    """Collect CPU, RAM, and disk metrics without psutil.

    Args:
        root: Directory for disk usage check. Defaults to current working directory.

    Returns:
        dict with keys (varies by platform):
          cpu_percent: int | None    — Windows CPU usage %
          cpu_load_1m/5m/15m: float  — Linux load averages
          ram_percent: float | None  — Memory used %
          ram_used_mb: int | None    — Memory used (MB)
          ram_free_mb: int | None    — Memory free (MB)
          ram_total_mb: int | None   — Total memory (MB)
          disk_percent: float | None — Disk used %
          disk_used_gb: float | None — Disk used (GB)
          disk_free_gb: float | None — Disk free (GB)
          disk_total_gb: float | None — Disk total (GB)
    """
    metrics: dict = {}
    root = root if root is not None else Path.cwd()

    # ── CPU ───────────────────────────────────────────
    try:
        if os.name == "nt":
            r = subprocess.run(
                "wmic cpu get LoadPercentage /value",
                shell=True, capture_output=True, text=True, timeout=3,
            )
            for line in r.stdout.splitlines():
                if line.strip().startswith("LoadPercentage="):
                    metrics["cpu_percent"] = int(line.split("=")[1].strip())
        else:
            load = os.getloadavg()
            metrics["cpu_load_1m"] = round(load[0], 2)
            metrics["cpu_load_5m"] = round(load[1], 2)
            metrics["cpu_load_15m"] = round(load[2], 2)
    except Exception:
        metrics["cpu_percent"] = None

    # ── Memory ────────────────────────────────────────
    try:
        if os.name == "nt":
            r = subprocess.run(
                "wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /value",
                shell=True, capture_output=True, text=True, timeout=3,
            )
            free_kb = total_kb = None
            for line in r.stdout.splitlines():
                line_s = line.strip()
                if line_s.startswith("FreePhysicalMemory="):
                    free_kb = int(line_s.split("=")[1])
                elif line_s.startswith("TotalVisibleMemorySize="):
                    total_kb = int(line_s.split("=")[1])
            if free_kb is not None and total_kb is not None:
                metrics["ram_total_mb"] = round(total_kb / 1024)
                metrics["ram_free_mb"] = round(free_kb / 1024)
                metrics["ram_used_mb"] = round((total_kb - free_kb) / 1024)
                metrics["ram_percent"] = round((total_kb - free_kb) / total_kb * 100, 1)
        else:
            with open("/proc/meminfo") as f:
                mem = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        mem[key] = int(parts[1])
                total = mem.get("MemTotal", 0)
                free = mem.get("MemAvailable", mem.get("MemFree", 0))
                if total:
                    metrics["ram_total_mb"] = round(total / 1024)
                    metrics["ram_free_mb"] = round(free / 1024)
                    metrics["ram_used_mb"] = round((total - free) / 1024)
                    metrics["ram_percent"] = round((total - free) / total * 100, 1)
    except Exception:
        metrics["ram_percent"] = None

    # ── Disk ──────────────────────────────────────────
    try:
        usage = shutil.disk_usage(str(root))
        metrics["disk_total_gb"] = round(usage.total / (1024 ** 3), 1)
        metrics["disk_used_gb"] = round(usage.used / (1024 ** 3), 1)
        metrics["disk_free_gb"] = round(usage.free / (1024 ** 3), 1)
        metrics["disk_percent"] = round(usage.used / usage.total * 100, 1)
    except Exception:
        metrics["disk_percent"] = None

    return metrics
