# Extraction Plan — SmokeOS Core (Public)

Extracted from private `smokeos-local` on 2026-07-09.

## PUBLIC (included as-is)

### backend/core/ (12 files)
| File | Description |
|------|-------------|
| atomic_write.py | Atomic file writer (tmp->bak->replace with SHA256) |
| ports.py | Canonical port registry |
| signals.py | OS signal handlers (cross-platform) |
| json_io.py | JSON I/O with BOM-safe encoding |
| colors.py | ANSI terminal color constants |
| env.py | Environment utilities (UTF-8, truthy, hostname) |
| logging_config.py | Shared logging configuration |
| quality_gate.py | Web code quality validator |
| system_utils.py | Cross-platform system utilities |
| process_supervisor.py | Supervised process registry |
| heartbeat.py | Agent heartbeat protocol (dataclass + protocol) |
| event_store.py | SQLite-backed event store |

### NEEDS SANITIZATION (included after fix)
| File | Fix |
|------|-----|
| task_queue.py | Hardcoded `(project root)/state` -> relative path |

### Governance (.ai/ — 6 files)
- AI_RULES.md, ARCHITECTURE.md, CODING_STANDARD.md, DECISION_LOG.md, DIRECTORY_RULES.md, ROADMAP.md

### Tools (3 files)
- smoke_doctor.py, manifest_generator.py, archaeologist.py

### Docs (4 files)
- architecture.md, features.md, operator_guide.md, operator-quickstart.md

## PRIVATE (excluded)

### backend/ (400+ files excluded)
| Directory | Reason |
|-----------|--------|
| backend/trading/ | Trading strategies (Robinhood, buy dips, beat arbitrage) |
| backend/api/ | API routes (phone gateway, dashboard, trading endpoints) |
| backend/agents/ | Agent orchestration (references personal infrastructure) |
| backend/connectors/ | External connectors (Robinhood, Discord, Slack) |
| backend/stock_loops/ | Automated trading loops |
| backend/core/auth.py | Authentication with secrets |
| backend/core/config.py | Machine-specific config with API keys |
| backend/core/freellm_auth.py | FreeLLM token management |
| backend/core/freellm_key_scraper.py | API key scraping |
| backend/core/key_rotator.py | API key rotation |
| backend/core/obsidian_vault.py | Personal Obsidian paths |
| backend/core/cron_scheduler.py | Personal paths |
| backend/core/fiverr_wrapper.py | Fiverr integration (private) |
| backend/core/fl_studio_bridge.py | FL Studio bridge (private) |
| backend/core/cloud_sync.py | Cloud sync (private infra) |
| backend/core/dashboard_server.py | Dashboard server (private infra) |
| backend/core/config_constants.py | Imports from config.py (secrets) |
| backend/core/unified_event_bus.py | References trading/phone event types |
| backend/core/process_watchdog.py | References node_registry (local paths) |
| backend/core/agent_*.py | Agent orchestration (private) |
| backend/core/memory_*.py | Memory systems (private) |
| backend/core/cognitive_*.py | Cognitive integrity (private) |
| All other backend/core/*.py | Unaudited — default to private |

### plugins/ (218 files excluded)
| Directory | Reason |
|-----------|--------|
| plugins/robinhood/ | Robinhood trading integration |
| plugins/technical_indicators/ | Trading indicators |
| plugins/backtest/ | Backtesting engine |
| plugins/alt_data/ | Alternative financial data |
| plugins/market_*/ | Market data plugins |
| plugins/regime/ | Trading regime detection |
| plugins/discord/ | Discord bot (private) |

### docs/ (excluded)
| File | Reason |
|------|--------|
| docs/PHONE_API_CONTRACT.json | Phone gateway API (private infra) |
| docs/PHONE_CONTROL_DESIGN.md | Phone control (private infra) |

## VERIFICATION

- [x] No `C:\Users\Quixk` paths in any included file
- [x] No API tokens or keys in any included file
- [x] No trading logic in any included file
- [x] No .env, .token, or credential files
- [x] All included files are generic framework/runtime code

## Total

- **Included**: 27 files (~200 KB)
- **Excluded**: 600+ files (~9 MB)
- **Extraction ratio**: ~4% of private repo
