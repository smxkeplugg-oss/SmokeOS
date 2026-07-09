# SmokeOS Founder Dashboard Architecture

## Overview
The Founder Dashboard is the central nervous system of SmokeOS — a single-file HTML dashboard that monitors, controls, and visualizes the entire AI agent ecosystem.

## Files
| File | Purpose | Lines | Status |
|------|---------|-------|--------|
| `founder_dashboard.html` | Primary dashboard — 32 nodes, AI consciousness, watchdog, log viewer | ~3053 | Active |
| `founder_infinite_v2.html` | Next-gen dashboard — endpoint grid, agent inboxes, swarm heartbeat | ~800 | Active |
| `aiengine_cli.py` | Unified CLI — launch, stop, status, logs, search, sync, dashboard | ~464 | Active |
| `start.py` | Bootstrap server — serves dashboards, manages processes | Unknown | Referenced |

## Dashboard v1 Architecture (founder_dashboard.html)

### Layers
1. **Boot Sequence** — Animated terminal overlay, progress bar, consciousness initialization
2. **Header** — Title, session info, clock, version badge, theme toggle
3. **Status Bar** — Live stats, connection indicators, refresh/diagnose/hook buttons, emergency stop
4. **AI Consciousness Panel** — System awareness, anomaly detection, predictive index, entropy, thought stream
5. **Search/Filter** — Global node search, category filters, result count
6. **Category Stats** — Per-category health bars with click-to-filter
7. **Activity Timeline** — 60-point health history bar chart
8. **Watchdog Panel** — CPU/RAM/Disk gauges, uptime tracker, process table, event log
9. **Log Viewer** — Service log browser with search, auto-refresh, syntax highlighting
10. **Node Grid** — 32 registered nodes in category groups, with modals and actions
11. **Command Palette** — Ctrl+K searchable command interface
12. **Sync Log** — Timestamped event stream
13. **Toast Notifications** — Ephemeral alert system

### Data Flow
```
REGISTRY (32 nodes) → renderNodes() → DOM Grid
REGISTRY → checkPortStatus() → port_alive → REGISTRY._alive
REGISTRY → updateCardsFromRegistry() → card state update
Watchdog API → renderWatchdog() → gauges + proc table + events
WebSocket/SSE → real-time updates → hot reload, registry sync
AI Consciousness → metricsHistory + activityTimeline → predictive analysis
```

### State Management
- `REGISTRY` — canonical node definitions + runtime `_alive` state
- `metricsHistory` — rolling window of CPU, RAM, Disk, Running counts
- `activityTimeline` — 60-point health percentage history
- `aiThoughts` — rolling log of AI consciousness messages
- `currentFilter` — active search filter ('all', 'running', 'stopped', etc.)
- `serverConnected`, `wsConnected` — connection state flags

### Known Issues
- `const procs` redeclared in renderWatchdog (strict mode SyntaxError risk)
- filterLogOutput clobbers textContent on search clear
- WS_PORT calculation produces NaN when served via file://
- Emergency stop countdown timing drift (1.5s actual vs intended 3s)
- hot reload indicator not wired to actual file watcher

## Dashboard v2 Architecture (founder_infinite_v2.html)

### Layers
1. **Endpoint Grid** — Live health checks of all system endpoints
2. **Agent Grid** — Live inbox status for 6 agents (hermes, claude, gemini, cursor, goose)
3. **Instagram Transcripts** — Reel transcription browser
4. **Task Queue** — In-flight task visualization
5. **Swarm Heartbeat** — Message rate visualization, 60s rolling window
6. **Canonical Tree** — File system status (live/replica/archive)
7. **Burn Rate** — Resource utilization metrics
8. **Goals/Vector** — Strategic priority display
9. **Action Buttons** — One-click commands (pulse agents, run transcriber, etc.)
10. **Log Stream** — Live log tail

### Data Flow
```
Kernel :3421 → /health, /system/status, /agents/inbox/{name}
Static files → outputs/instagram_transcripts/
Local polling → endpoint checks every 5s
Agent polling → inbox checks every 7s
Task polling → task list every 11s
```

## CLI Architecture (aiengine_cli.py)

### Commands
| Command | Function |
|---------|----------|
| `list` / `ls` | List all nodes with status |
| `status` / `st` | Detailed node status table |
| `health` | System health summary |
| `search <query>` | Fuzzy search nodes |
| `logs <node>` | Tail logs for node |
| `launch [node]` | Launch core nodes or specific node |
| `stop <node>` | Stop node by port/PID |
| `restart <node>` | Stop + start node |
| `sync [--watch]` | Cloud sync one-shot or continuous |
| `dashboard` / `db` | Open dashboard in browser |
| `nodes` / `registry` | Dump full registry JSON |

### Design Patterns
- Registry-driven: all node metadata in `node_registry.json`
- Port-centric: health determined by TCP port availability
- Fuzzy matching: node names resolved by substring match
- Interactive mode: REPL with `aiengine>` prompt

## Integration Points
| Source | Destination | Method |
|--------|-------------|--------|
| Dashboard → Kernel | `:3421/health` | HTTP fetch |
| Dashboard → Watchdog | `:9999/dashboard/health` | HTTP fetch |
| Dashboard → Kernel | `:9998` (DASH_PORT-1) | WebSocket |
| Dashboard → Kernel | `:9998` fallback | SSE |
| CLI → Node processes | Direct subprocess | `subprocess.Popen` |
| CLI → Browser | `webbrowser.open` | OS default browser |
| v2 Dashboard → Kernel | `:3421` | HTTP fetch (CORS) |

## Evolution Targets
1. **Modularize** — Split 3053-line monolith into component files
2. **Backend API** — Standardize all dashboard data behind REST/WebSocket API
3. **State Sync** — Real-time sync between all dashboard instances
4. **Plugin System** — Allow dynamic panel registration
5. **Multi-tenancy** — Support multiple founder profiles
6. **AI Integration** — Dashboard itself has AI copilot for diagnostics
