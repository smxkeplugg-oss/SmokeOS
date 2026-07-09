# Smoke OS Agent OS — Operator Guide (1 page)

> Goal: take a fresh operator from "I just cloned this repo" to "I see
> the system running" in under 5 minutes.

Roadmap master: [`docs/singular-dashboard.md`](singular-dashboard.md).
Cloud-sync details: [`docs/aistudio_smokeos_sync.md`](aistudio_smokeos_sync.md).
This file is the **one-screen quickstart** — print and pin next to your
monitor.

---

## 0. Pre-flight (only if a previous boot left zombies)

If PM2 services are hung:

```powershell
pm2 kill
```

If that doesn't work, manually kill python processes:

```powershell
Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%kernel.py%' OR CommandLine LIKE '%orchestrator.py%' OR CommandLine LIKE '%sync_bridge.py%'" |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

---

## 1. Pull the repo & install

```bash
git clone <your-fork-url>
cd aiengine
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

## 2. Boot the system

```cmd
:: Windows one-click (6-phase bootstrap: venv → frontend → .env → PM2 → verify → browser)
start.bat
```

Or manually:

```bash
pm2 start ecosystem.config.cjs
```

This boots 21 services including:
- **kernel** on :3421 (FastAPI — agent orchestration, plugin system, MCP)
- **local-orchestrator** on :3499 (stdlib HTTP — CLI, dashboards, cloud sync)
- **sync-bridge** (cloud sync daemon)
- **frontend** on :3000 (Vite/React — Swarm Visor dashboard)

Your default browser opens `http://localhost:3421/v3/`.

---

## 3. Confirm the system is alive

```bash
# Kernel health
curl http://127.0.0.1:3421/health

# Orchestrator health
curl http://127.0.0.1:3499/health

# System status
curl http://127.0.0.1:3421/system/status

# Node list
curl http://127.0.0.1:3421/nodes
```

---

## 4. Explore the dashboards

| URL | What it shows |
|-----|--------------|
| `http://127.0.0.1:3421/v3/` | Swarm Visor — unified dashboard, agent monitoring, system controls |
| `http://127.0.0.1:3499/dashboard/robinhood` | Robinhood trading workspace — portfolio, watchlist, orders, news |
| `http://127.0.0.1:3499/dashboard/capital_lab` | Capital Lab — trading research and analysis |
| `http://127.0.0.1:3421/docs` | OpenAPI docs — full kernel API reference |

---

## 5. (Optional) Wire Google AI Studio cloud-sync

```cmd
set SMOKEOS_CLOUD_SYNC_URL=https://us-central1-aiplatform.googleapis.com/v1/projects/%GOOGLE_PROJECT%/locations/us-central1/endpoints/<ENDPOINT_ID>:predict
set GOOGLE_ACCESS_TOKEN=<ya29....>
pm2 restart sync-bridge
```

The sync bridge mirrors audit verdicts to your AI Studio endpoint as
JSON (fire-and-forget, 3 retries, 2 s timeout). See
[`docs/aistudio_smokeos_sync.md`](aistudio_smokeos_sync.md) for the
Vertex AI Custom Prediction Routine body.

---

## 6. Run tests

```bash
python -m pytest tests/ -v
```

Expect all tests to pass.

---

## 7. Tear down

```cmd
:: Stop all services
pm2 stop all

:: Or completely kill PM2
pm2 kill
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Port 3421 in use | Stale kernel process | `pm2 restart kernel` or `pm2 kill && start.bat` |
| Port 3499 in use | Stale orchestrator | `pm2 restart local-orchestrator` |
| Services not starting | Missing .env | Copy `.env.example` → `.env` (start.bat does this automatically) |
| Frontend 404 | Vite not built | `cd frontend && npm install && npm run build` |
| Browser shows stale data | Cached response | `Ctrl+Shift+R` |

---

## 9. Where to go next

- Try the AI Studio cloud-sync recipe (Step 5).
- Content playbook: [`docs/content_playbook.md`](content_playbook.md) for the
  business-side followups.
- Roadmap: [`docs/singular-dashboard.md`](singular-dashboard.md) for the
  master plan.
