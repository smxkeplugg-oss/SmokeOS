# SmokeOS Core

Open-source framework for AI agent orchestration. This is the public core extracted from the private [smokeos-local](https://github.com/smxkeplugg-oss/smokeos-local) monorepo.

## Structure

```
backend/core/     Framework runtime (atomic I/O, event store, task queue, ports, signals, heartbeat)
.ai/              AI governance (rules every agent must follow before editing code)
docs/             Architecture and operator guides
tools/            Framework utilities (smoke doctor, archaeologist, manifest generator)
```

## What's NOT here

This repo contains only the reusable framework. The following live in the private repo:
- Trading strategies and market data plugins
- Phone gateway and SMS integration
- Machine-specific configuration (PM2, ecosystem configs, API keys)
- Robinhood integration
- Cloud sync and local orchestration

## Quick Start

```bash
# Audit your machine for SmokeOS-related folders
python tools/smoke_doctor.py

# Scan the codebase for orphans and duplicates
python tools/archaeologist.py
```

## Governance

Every AI agent MUST read `.ai/AI_RULES.md` before editing any code in this project.

## License

MIT
