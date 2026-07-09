# DIRECTORY_RULES.md — What AIs Can and Cannot Touch

## ✅ EDITABLE

| Directory | Caution |
|-----------|---------|
| smokeos_local/plugins/ | Plugin isolation |
| SmokeOS/coordination/ | Atomic writes only |
| backend/trading/ | Run pytest after edits |
| capital_lab/ | Don't delete survivor data |
| tests/ | Add tests, don't remove |
| docs/ | Keep up to date |
| swarm_visor/ | Vite/React conventions |

## 🔒 READ ONLY

| File/Dir | Why |
|----------|-----|
| SmokeOS/guardrails.py | Pre-trade safety |
| SmokeOS/phone_gateway.py | Bearer token auth |
| SmokeOS/autonomous_trader.py | Live trading loop |
| SmokeOS/remote_kill_switch.py | Emergency shutdown |
| smokeos_local/core/ | 7-layer platform kernel |
| smokeos_local/config.json | Vault path, ports, cloud URLs |
| backend/kernel.py | Main API (port 3421) |
| backend/core/signals.py | Shutdown handlers |
| backend/arbitrage_scanner.py | Background daemon |
| backend/system_monitor.py | Background daemon |
| backend/disk_cleaner.py | Background daemon |
| .smokeos_state/ | Runtime tokens, kill flags |

## ⚠️ CAUTION (verify with human)

| File | Why |
|------|-----|
| ecosystem.config.cjs | 14 PM2 services. Changes require restart + verify |
| .gitignore | Last defense against secret leaks |
| tools/archaeologist.py | Governance tool — scanner. Editing disables project inventory. |
| tools/change_ledger.py | Governance tool — ledger. Editing disables change tracking. |

## 🚫 FORBIDDEN

| Path | Why |
|------|-----|
| robinhood-for-agents/ | Auth submodule with .token |
| .env | Live API keys (gitignored) |
| discord.json | Bot token (gitignored) |
| config/ai_keys.json | API keys (gitignored) |
| freellmapi.token | LLM API token (gitignored) |

---
*Part of SmokeOS Governance Layer.*
