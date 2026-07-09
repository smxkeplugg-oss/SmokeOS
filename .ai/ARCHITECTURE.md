# ARCHITECTURE.md — SmokeOS System Map

## Port Map

| Port | Service | File |
|------|---------|------|
| 3421 | Kernel API | backend/kernel.py |
| 3499 | Orchestrator | smokeos_local/orchestrator.py |
| 3440 | Phone Gateway | SmokeOS/phone_gateway.py |
| 3430 | Alt API / Bridge | — |
| 3000 | Frontend (Vite) | swarm_visor/ |
| 8765 | Command Center Dashboard | SmokeOS/command_center.py |
| 9999 | Dashboard | start.py |

## Directory Map

```
SmokeOS/           — Trading core (autonomous_trader, guardrails, phone_gateway, claude_bridge)
smokeos_local/     — Local platform (orchestrator, sync_bridge, obsidian_sync, 7-layer core)
backend/           — Shared backend (kernel.py, trading/, core/)
capital_lab/       — Research workspace (backtesting, strategy evolver)
swarm_visor/       — React/Vite dashboard
swarm_nexus/       — Agent swarm coordination
tools/             — Utility scripts (archaeologist, etc.)
.ai/               — AI governance (this directory)
.github/           — CI/CD, templates
```

## Dual-Grid Architecture

- **Cloud Grid (Google AI Studio)**: Orchestration plane. Gemini maintains React SPA, MCPOP3 protocol, swarm_bus.json.
- **Local Grid (This Node)**: Execution authority. Handles trading, PC automation, PM2 supervision.
- **Communication**: Cloud → Local via swarm_bus.json. Local → Cloud via sync_outbox.md.

## PM2 Services (14 total)

kernel, unified-sync, dashboard, frontend, autonomous-agent, autonomous-core, commercial, arbitrage-scanner, system-monitor, disk-cleaner, watchdog, health-check, analytics-tracker, cloud-sync

## Key Dependencies

- **Python**: 3.12+, FastAPI, uvicorn, httpx, pydantic
- **Node**: swarm_visor (Vite/React/TypeScript)
- **AI**: Ollama (local), Claude Code CLI, Gemini API
- **Trading**: Robinhood MCP, paper_trading, guardrails
- **Infra**: PM2 (process manager), SQLite, Obsidian vault

---
*Part of SmokeOS Governance Layer.*
