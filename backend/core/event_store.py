"""Event Store
============
Single source of truth for every agent execution on the kernel.

Per CTO directive (2026-07-03): NO fake data — every row written here is a
real execution log produced by a real agent. Dashboards read exclusively from
this table (no in-memory stubs).

Storage
-------
SQLite at ``state/events.db`` in **WAL journal mode** so concurrent agents
can POST without blocking the dashboard's GET /events.

Schema (exact 7 columns, no extras)
-----------------------------------
  id        TEXT PRIMARY KEY  (uuid4 hex)
  timestamp TEXT NOT NULL      (ISO-8601 UTC, e.g. "2026-07-03T02:11:34.812Z")
  agent     TEXT NOT NULL      (name registered in /agents)
  action    TEXT NOT NULL      (verb-noun, e.g. "clinical_audit")
  result    TEXT NOT NULL      (one of "ok","success","failed","timeout")
  duration  REAL NOT NULL      (whole-action duration in seconds, finite & >=0)
  cost      REAL NOT NULL      (USD spent; 0.0 = free / local; finite & >=0)

Endpoints (mounted at ``/events``)
------------------------------------
POST /events         Write one event row.
                     Body {agent, action, result, duration, cost}.
                     Returns 200 with the row that was persisted.

GET  /events         List events (latest first).
                     Query: limit (1..200, default 50), agent, action filters.

GET  /events/stats   Aggregate: totals + by_agent breakdown (cost desc).

Money Impact
------------
Every dollar spent by an agent is recorded here; cost aggregation is the
source of truth for agent spend dashboards. A missing row means the action
did NOT happen — the table is the audit log.
"""
from __future__ import annotations

import math
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

# ── Storage paths ──────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATE_DIR = BASE_DIR / "state"
EVENTS_DB = STATE_DIR / "events.db"

router = APIRouter(tags=["event-store"])

_ALLOWED_RESULTS = ("ok", "success", "failed", "timeout")


def _now_iso() -> str:
    """UTC ISO-8601 with millisecond precision and 'Z' suffix."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _ensure_db() -> None:
    """Create the events schema + indexes if absent. Idempotent.
    Sets WAL journal mode so concurrent agents can POST without HEAD-of-line
    blocking the dashboard GET. Run once per connection; sqlite caches the
    journal-mode pragma in the file header after first write so re-runs are
    cheap (a no-op dispatch)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(EVENTS_DB)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id        TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                agent     TEXT NOT NULL,
                action    TEXT NOT NULL,
                result    TEXT NOT NULL,
                duration  REAL NOT NULL,
                cost      REAL NOT NULL
            )
            """
        )
        # WAL mode for concurrent readers + non-blocking writers.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_ts ON events (timestamp DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_agent ON events (agent)"
        )
        conn.commit()


def _validate_event(body: Dict[str, Any]) -> Dict[str, Any]:
    """Pull + coerce + default every required field. Raise HTTPException(400)
    on missing/invalid fields. Rejects NaN, +inf, and negative."""
    required = ("agent", "action", "result", "duration", "cost")
    missing = [k for k in required if k not in body]
    if missing:
        raise HTTPException(status_code=400, detail=f"missing required fields: {missing}")

    _agent = str(body["agent"]).strip()
    if not _agent:
        raise HTTPException(400, "agent must be non-empty")

    _action = str(body["action"]).strip()
    if not _action:
        raise HTTPException(400, "action must be non-empty")

    _result = str(body["result"]).lower().strip()
    if _result not in _ALLOWED_RESULTS:
        raise HTTPException(
            400,
            f"result must be one of {list(_ALLOWED_RESULTS)} (got {body['result']!r})",
        )

    try:
        _duration = float(body["duration"])
    except (TypeError, ValueError):
        raise HTTPException(400, "duration must be a number (seconds)")
    if not math.isfinite(_duration) or _duration < 0:
        raise HTTPException(400, "duration must be a finite, non-negative number (seconds)")

    try:
        _cost = float(body["cost"])
    except (TypeError, ValueError):
        raise HTTPException(400, "cost must be a number (USD)")
    if not math.isfinite(_cost) or _cost < 0:
        raise HTTPException(400, "cost must be a finite, non-negative number (USD)")

    return {
        "agent": _agent,
        "action": _action,
        "result": _result,
        "duration": _duration,
        "cost": _cost,
    }


@router.post("")
async def post_event(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Write one event row. Returns the row that was persisted.

    Response shape::
        {"ok": true, "event": {"id": "...", "timestamp": "...", ...}}
    """
    fields = _validate_event(data)
    row = {
        "id": uuid.uuid4().hex,
        "timestamp": _now_iso(),
        **fields,
    }
    _ensure_db()
    with sqlite3.connect(str(EVENTS_DB)) as conn:
        conn.execute(
            """
            INSERT INTO events (id, timestamp, agent, action, result, duration, cost)
              VALUES (:id, :timestamp, :agent, :action, :result, :duration, :cost)
            """,
            row,
        )
        conn.commit()
    return {"ok": True, "event": row}


@router.get("")
async def get_events(
    limit: int = Query(default=50, ge=1, le=200),
    agent: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    """List events newest-first.

    Query params:
      limit  cap rows returned (1..200, default 50)
      agent  optional exact-match agent filter
      action optional exact-match action filter

    Response shape::
        {"ok": true, "count": N, "events": [{...}, ...]}
    """
    # Honour the spec: spec asks for GET /events + GET /events/stats. The
    # prefix="/events" + decorator "" mounts at exactly /events.
    _ensure_db()
    sql = (
        "SELECT id, timestamp, agent, action, result, duration, cost "
        "FROM events"
    )
    clauses: List[str] = []
    params: List[Any] = []
    if agent:
        clauses.append("agent = ?")
        params.append(agent)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    with sqlite3.connect(str(EVENTS_DB)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    events = [dict(r) for r in rows]
    return {"ok": True, "count": len(events), "events": events}


@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """Aggregate by agent: row count, total duration (seconds), total cost (USD).

    Response shape::
        {
          "ok": true,
          "totals":   {"events": N, "duration_s": S, "cost_usd": C},
          "by_agent": [{"agent": "...", "events": N,
                        "duration_s": S, "cost_usd": C}, ...]
        }
    """
    _ensure_db()
    with sqlite3.connect(str(EVENTS_DB)) as conn:
        by_agent_rows = conn.execute(
            """
            SELECT agent,
                   COUNT(*)     AS events,
                   SUM(duration) AS duration_s,
                   SUM(cost)     AS cost_usd
            FROM events
            GROUP BY agent
            ORDER BY cost_usd DESC, events DESC
            """
        ).fetchall()
        grand = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(duration),0), COALESCE(SUM(cost),0) "
            "FROM events"
        ).fetchone()
    return {
        "ok": True,
        "totals": {
            "events": grand[0],
            "duration_s": round(grand[1], 3),
            "cost_usd": round(grand[2], 6),
        },
        "by_agent": [
            {
                "agent": r[0],
                "events": r[1],
                "duration_s": round(r[2], 3),
                "cost_usd": round(r[3], 6),
            }
            for r in by_agent_rows
        ],
    }
