"""
backend/core/ports.py — Canonical port registry for SmokeOS
===========================================================
Single source of truth for every TCP port used by SmokeOS services.
Extracted from 25+ hardcoded locations across the codebase.

Every other module should import from here instead of hardcoding port
numbers. The config singleton (``backend.core.config.cfg``) reads env-var
overrides at startup, so ``KERNEL_PORT`` etc. respect the user's
``KERNEL_PORT`` env var.

Usage::

    from backend.core.ports import KERNEL_PORT, DASHBOARD_PORT
    uvicorn.run(app, host="127.0.0.1", port=KERNEL_PORT)

Design invariants:
  - Constants are module-level (import once, no runtime recomputation).
  - Each constant has a documented origin so future devs know where it's used.
  - Env-var overrides are resolved ONCE at import time via config.py.
  - Never exposes secrets or API keys (those belong in config.py).

Author: FreeBuff Phase 1 consolidation
"""

from __future__ import annotations

import os

# ── Helpers ──────────────────────────────────────────────────────

def _env_port(name: str, default: int) -> int:
    """Read an env-var port, falling back to *default* on missing or invalid."""
    raw = os.environ.get(name, "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return default


# ════════════════════════════════════════════════════════════════
# CORE PORTS
# ════════════════════════════════════════════════════════════════

# Kernel (FastAPI app serving /sap/v1, /ws, /api/*)
# Origin: backend/kernel.py:3277, start.py, smokeos_one.py:DEFAULT_KERNEL_PORT
KERNEL_PORT = _env_port("KERNEL_PORT", 3421)

# Paper RH simulator (paper trading dashboard on Starlette)
# Origin: logs/paper_rh_simulator.py:69, smokeos_one.py:DEFAULT_SIM_PORT
PAPER_RH_SIM_PORT = _env_port("PAPER_RH_SIM_PORT", 3499)

# Frontend (Vite dev server)
# Origin: start.py:556 (args.port), start_all.py:SERVICES[1]["port"]
FRONTEND_PORT = _env_port("FRONTEND_PORT", 3000)

# Dashboard (ThreadingHTTPServer for /dashboard/health, watchdog status, SSE)
# Origin: backend/core/dashboard_server.py:DEFAULT_DASHBOARD_PORT, start.py:DASHBOARD_PORT
DASHBOARD_PORT = _env_port("DASHBOARD_PORT", 9999)

# WebSocket Event Bus (realtime push to dashboard)
# Origin: backend/core/process_watchdog.py:63, dashboard_server.py:655 (ws_port = dashboard - 1)
WS_EVENT_BUS_PORT = _env_port("WS_EVENT_BUS_PORT", 9998)

# MCP server (Model Context Protocol bridge)
# Origin: backend/mcp/server.py:DEFAULT_PORT
MCP_PORT = _env_port("MCP_PORT", 3430)


# ════════════════════════════════════════════════════════════════
# GATEWAY / BRIDGE PORTS
# ════════════════════════════════════════════════════════════════

# Phone gateway (Twilio/SMS integration)
# Origin: smokeos/phone_gateway.py:DEFAULT_PORT
PHONE_GATEWAY_PORT = _env_port("PHONE_GATEWAY_PORT", 3440)

# OMNI exec (legacy executor from zos/ tree, port 3420)
# Origin: zos/smokeos-agent(11)/backend/backend/kernel.py
OMNI_EXEC_PORT = _env_port("OMNI_EXEC_PORT", 3420)

# Bridge (local sync bridge from zos/ tree)
# Origin: zos/smokeos-agent(11)/backend/backend/bridge.py
BRIDGE_PORT = _env_port("BRIDGE_PORT", 3430)

# Fairy / God legacy sidecars (zos/ tree)
# Origin: zos/smokeos-agent(11)/backend/backend/fairy.py, god.py
FAIRY_PORT = _env_port("FAIRY_PORT", 8420)
GOD_PORT = _env_port("GOD_PORT", 8002)


# ════════════════════════════════════════════════════════════════
# SIDECAR / DAEMON PORTS
# ════════════════════════════════════════════════════════════════

# Infinite routes sidecar (extra endpoints on dedicated port)
# Origin: start.py:INFINITE_SIDECAR_PORT, backend/infinite_routes.py
INFINITE_SIDECAR_PORT = _env_port("INFINITE_SIDECAR_PORT", 3423)

# Harness (aiengine test harness)
# Origin: aiengine/harness/server.py
HARNESS_PORT = _env_port("HARNESS_PORT", 3422)

# Sync daemon health endpoint (cloud_sync health check)
# Origin: backend/core/cloud_sync.py:health endpoint
SYNC_DAEMON_HEALTH_PORT = _env_port("SYNC_DAEMON_HEALTH_PORT", 3422)

# SmokeOS local orchestrator (stdlib HTTP server for dashboards, CLI)
# Origin: smokeos_local/orchestrator.py, start_smokeos_local.py
LOCAL_STATUS_PORT = _env_port("LOCAL_STATUS_PORT", 8765)

# Discord bot port listener
# Origin: zos/smokeos-agent(11)/backend/discord_bot.py:run_port_listener
DISCORD_LISTENER_PORT = _env_port("DISCORD_LISTENER_PORT", 3425)


# ════════════════════════════════════════════════════════════════
# EXTERNAL / DEPENDENCY PORTS
# ════════════════════════════════════════════════════════════════

# Ollama (local LLM server)
# Origin: backend/kernel.py:_OLLAMA_BASE, backend/core/config.py
OLLAMA_PORT = _env_port("OLLAMA_PORT", 11434)

# FreeLLM API (local LLM aggregator)
# Origin: backend/core/config.py
FREELLM_BASE_PORT = _env_port("FREELLM_BASE_PORT", 3001)

# Egress proxy (outbound caching proxy)
# Origin: _safe_to_delete_2026/backend/cage/egress_proxy.py
EGRESS_PORT = _env_port("EGRESS_PORT", 3128)

# Mock cloud (local dev server)
# Origin: mock_cloud.py
MOCK_CLOUD_PORT = _env_port("MOCK_CLOUD_PORT", 18080)


# ════════════════════════════════════════════════════════════════
# PORT RANGE RESERVATIONS
# ════════════════════════════════════════════════════════════════

# The canonical ordering of SmokeOS services on localhost.
# Useful for port-allocation logic and health checks.
SMOKEOS_SERVICE_PORTS: list[int] = [
    KERNEL_PORT,            # 3421
    HARNESS_PORT,           # 3422
    INFINITE_SIDECAR_PORT,  # 3423
    DISCORD_LISTENER_PORT,  # 3425
    MCP_PORT,               # 3430
    PHONE_GATEWAY_PORT,     # 3440
    PAPER_RH_SIM_PORT,      # 3499
    LOCAL_STATUS_PORT,      # 8765
    SYNC_DAEMON_HEALTH_PORT,# 3422
    WS_EVENT_BUS_PORT,      # 9998
    DASHBOARD_PORT,         # 9999
]

# Dashboard auto-fallback ports (when DASHBOARD_PORT is in use)
DASHBOARD_FALLBACK_PORTS: list[int] = [9999, 9998, 9997, 9996, 8888]


def all_ports() -> dict[str, int]:
    """Return a dict of all known SmokeOS ports (name → port).

    Useful for ``--print-config`` and diagnostics dashboards.
    """
    return {
        "kernel": KERNEL_PORT,
        "paper_rh_sim": PAPER_RH_SIM_PORT,
        "frontend": FRONTEND_PORT,
        "dashboard": DASHBOARD_PORT,
        "ws_event_bus": WS_EVENT_BUS_PORT,
        "mcp": MCP_PORT,
        "phone_gateway": PHONE_GATEWAY_PORT,
        "infinite_sidecar": INFINITE_SIDECAR_PORT,
        "harness": HARNESS_PORT,
        "local_status": LOCAL_STATUS_PORT,
        "sync_health": SYNC_DAEMON_HEALTH_PORT,
        "discord_listener": DISCORD_LISTENER_PORT,
        "ollama": OLLAMA_PORT,
        "freellm_base": FREELLM_BASE_PORT,
    }
