# Smoke OS Agent OS — operator quickstart

> One page for the operator who cloned the repo and never read
> `docs/singular-dashboard.md`.
> Long-form roadmap lives in `docs/singular-dashboard.md`; this page is the
> orientation tour.

## TL;DR

```cmd
start.bat
:: Boots PM2 (21 services), then opens http://127.0.0.1:3421/v3/ in your browser.
```

That's it. The kernel dashboard shows live system status, agent monitoring,
topology, and the Robinhhood trading workspace.

For the orchestrator's health check and financial dashboards, open
<http://127.0.0.1:3499/health>.

---

## (a) Architecture overview

SmokeOS runs as 21 PM2-managed services. The two primary surfaces are:

| Service | Port | Role |
|---------|------|------|
| **Kernel** (FastAPI) | :3421 | Agent orchestration, plugin system, MCP, event store, topology |
| **Orchestrator** (stdlib HTTP) | :3499 | CLI, plugin dispatch, cloud sync, Capital Lab, Robinhood dashboards |

The kernel is the brain; the orchestrator is the body. They communicate via
cross-imports and the unified event bus.

---

## (b) Key endpoints

### Kernel (:3421)

| Endpoint | Returns | When to use |
|----------|---------|-------------|
| `/health` | System health + uptime | Operator dashboard polling |
| `/nodes` | Node registry | Agent monitoring |
| `/system/status` | CPU/memory/port checks | Health diagnostics |
| `/api/topology` | Digital Twin live status (23 nodes) | System overview |
| `/docs` | OpenAPI docs | API exploration |

### Orchestrator (:3499)

| Endpoint | Returns | When to use |
|----------|---------|-------------|
| `/health` | Orchestrator health + local node status | Local node diagnostics |
| `/dashboard/robinhood` | Robinhood trading workspace | Financial dashboard |
| `/dashboard/capital_lab` | Capital Lab dashboard | Trading research |
| `/api/agents` | Orchestrator-internal agent registry | Plugin/workflow monitoring |

---

## (c) How to set up SMOKEOS_CLOUD_SYNC_URL against a Vertex AI Endpoint

When you set this env var, the sync bridge POSTs audit verdicts to that URL
on a fire-and-forget daemon thread (3 retries, 2 s timeout).

### Step 1 — set the env var (example: Windows CMD)

```cmd
set SMOKEOS_CLOUD_SYNC_URL=https://us-central1-aiplatform.googleapis.com/v1/projects/<PROJECT>/locations/us-central1/endpoints/<ENDPOINT_ID>:predict
set GOOGLE_ACCESS_TOKEN=<ya29.... OAuth bearer from `gcloud auth print-access-token`>
pm2 restart all
```

### Step 2 — drop a @functions_framework.http handler into your AI Studio notebook

```python
import functions_framework
from typing import Any, Mapping

@functions_framework.http
def summarise_audit(request):
    rec: Mapping[str, Any] = request.get_json(silent=True) or {}
    verdict = str(rec.get("verdict", "unknown"))
    err = str(rec.get("error_message", ""))
    hint = str(rec.get("hint", ""))
    if verdict == "clean":
        body = f"[LOCAL OK] Smoke OS booted clean on {rec.get('platform','?')}."
    elif verdict == "binary_missing":
        body = f"[LOCAL CARGO] {err[:200]}\nFIX: {hint[:200]}"
    else:
        body = f"[LOCAL {verdict.upper()}] {err[:200] or 'see issues[]'}"
    return (body, 200, {"Content-Type": "text/plain"})
```

### Step 3 — verify locally first

```bash
# Spin a local capture webhook on a side port.
python tests/fixtures/capture_webhook.py &
# Point SMOKEOS_CLOUD_SYNC_URL at it; restart services.
SMOKEOS_CLOUD_SYNC_URL=http://127.0.0.1:9999/webhook pm2 restart all
# In another shell, check the captured payload.
cat /tmp/cloud_sync_capture.json | python -c "import json,sys; print(json.load(sys.stdin)['verdict'])"
```

---

## Recovery cheatsheet

| Symptom | Fix |
|---------|-----|
| Kernel (3421) not responding | `pm2 restart kernel` |
| Orchestrator (3499) not responding | `pm2 restart local-orchestrator` |
| Dashboard shows stale data | Refresh the tab; if that fails, check `/health` directly |
| PM2 services stuck | `pm2 kill && start.bat` |

## See also

- `docs/singular-dashboard.md` — the long-form roadmap.
- `docs/aistudio_smokeos_sync.md` — the AI Studio cloud-sync recipe in standalone form.
- `ecosystem.config.cjs` — the PM2 supervisor config (21 services).
