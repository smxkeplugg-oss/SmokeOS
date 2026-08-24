"""
Agent Task Queue — System 4: Priority-based task management
============================================================
SQLite-backed priority queue with agent assignment, automatic retry,
dead letter queue, and real-time status tracking.

Endpoints:
  POST   /tasks              - Create task
  GET    /tasks              - List tasks (with filters)
  GET    /tasks/{id}         - Get task details
  PUT    /tasks/{id}         - Update task
  DELETE /tasks/{id}         - Delete task
  POST   /tasks/{id}/cancel  - Cancel task
  GET    /tasks/pending      - Get pending tasks
  GET    /tasks/running      - Get running tasks
  GET    /tasks/completed    - Get completed tasks
  GET    /tasks/failed       - Get failed tasks
  POST   /tasks/{id}/retry   - Retry failed task
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

router = APIRouter(prefix="/tasks", tags=["tasks"])

# ── Database ──────────────────────────────────────────────────────
DB_DIR = Path(__file__).resolve().parent.parent / "state"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "tasks.db"

_LOCK = threading.Lock()
_DEAD_LETTER_DIR = DB_DIR / "dead_letter"
_DEAD_LETTER_DIR.mkdir(parents=True, exist_ok=True)


def _get_db() -> sqlite3.Connection:
    """Get a thread-safe SQLite connection with WAL mode."""
    db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def _init_db() -> None:
    """Create tables and indexes if they don't exist."""
    db = _get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            workflow_id TEXT,
            agent_id TEXT,
            priority INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            action TEXT NOT NULL DEFAULT '',
            command TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,
            error TEXT,
            duration_ms REAL,
            retries INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            timeout_seconds INTEGER DEFAULT 300,
            metadata TEXT DEFAULT '{}'
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_status ON tasks(status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_priority ON tasks(priority)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_agent ON tasks(agent_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_created ON tasks(created_at)")
    db.commit()
    db.close()


_init_db()

# ── Valid status transitions ──────────────────────────────────────
VALID_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}
ALLOWED_TRANSITIONS = {
    "pending": {"running", "cancelled"},
    "running": {"completed", "failed", "cancelled"},
    "completed": set(),      # Terminal
    "failed": {"pending"},  # Can retry
    "cancelled": set(),      # Terminal
}


# ── Helpers ───────────────────────────────────────────────────────
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    if d.get("metadata") and isinstance(d["metadata"], str):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except json.JSONDecodeError:
            d["metadata"] = {}
    return d


def _move_to_dead_letter(task: Dict[str, Any], reason: str) -> None:
    """Move a permanently failed task to the dead letter queue."""
    dl_path = _DEAD_LETTER_DIR / f"{task['id']}.json"
    base_dir = _DEAD_LETTER_DIR.resolve()
    dl_path_resolved = dl_path.resolve()
    try:
        dl_path_resolved.relative_to(base_dir)
    except ValueError:
        raise Exception("Invalid file path")
    task["dead_letter_reason"] = reason
    task["dead_letter_at"] = _now()
    dl_path_resolved.write_text(json.dumps(task, indent=2, default=str), encoding="utf-8")


def _assign_agent() -> Optional[str]:
    """Find the best available agent for a task. Returns agent_id or None."""
    try:
        registry_path = DB_DIR / "agent_registry.json"
        if not registry_path.exists():
            return None
        agents = json.loads(registry_path.read_text(encoding="utf-8")).get("agents", {})
        # Find online agents sorted by priority (highest first), lowest task count
        online = sorted(
            [a for a in agents.values() if a.get("status") == "online"],
            key=lambda a: (-a.get("priority", 0), a.get("task_count", 0)),
        )
        return online[0].get("agent_id") if online else None
    except (json.JSONDecodeError, OSError, KeyError):
        return None


# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.post("")
async def create_task(
    action: str = Body(..., description="Task action/description"),
    priority: int = Body(default=0, ge=0, le=100),
    agent_id: Optional[str] = Body(default=None),
    workflow_id: Optional[str] = Body(default=None),
    command: str = Body(default=""),
    max_retries: int = Body(default=3, ge=0, le=10),
    timeout_seconds: int = Body(default=300, ge=1, le=3600),
    metadata: Optional[Dict[str, Any]] = Body(default=None),
):
    """Create a new task in the queue. Auto-assigns to best available agent if none specified."""
    task_id = uuid.uuid4().hex[:16]

    # Auto-assign agent if not specified
    if not agent_id:
        with _LOCK:
            agent_id = _assign_agent()

    meta_json = json.dumps(metadata or {})

    with _LOCK:
        db = _get_db()
        db.execute(
            """INSERT INTO tasks (id, workflow_id, agent_id, priority, status, action, command,
               created_at, max_retries, timeout_seconds, metadata)
               VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)""",
            (task_id, workflow_id, agent_id, priority, action, command, _now(),
             max_retries, timeout_seconds, meta_json),
        )
        db.commit()

    task = _row_to_dict(db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    db.close()

    return {"ok": True, "task": task, "agent_assigned": bool(agent_id)}


@router.get("")
async def list_tasks(
    status: Optional[str] = Query(default=None, pattern="^(pending|running|completed|failed|cancelled)$"),
    agent_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """List tasks with optional filters."""
    db = _get_db()
    query = "SELECT * FROM tasks WHERE 1=1"
    params: list = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if agent_id:
        query += " AND agent_id = ?"
        params.append(agent_id)

    # Count
    count_row = db.execute(
        query.replace("SELECT *", "SELECT COUNT(*)"), params
    ).fetchone()
    total = count_row[0] if count_row else 0

    # Fetch
    query += " ORDER BY priority DESC, created_at ASC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = db.execute(query, params).fetchall()
    tasks = [_row_to_dict(r) for r in rows]
    db.close()

    return {"ok": True, "total": total, "count": len(tasks), "tasks": tasks}


@router.get("/{task_id}")
async def get_task(task_id: str):
    """Get a single task by ID."""
    db = _get_db()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return {"ok": True, "task": _row_to_dict(row)}


@router.put("/{task_id}")
async def update_task(
    task_id: str,
    priority: Optional[int] = Body(default=None, ge=0, le=100),
    agent_id: Optional[str] = Body(default=None),
    status: Optional[str] = Body(default=None),
    result: Optional[str] = Body(default=None),
    error: Optional[str] = Body(default=None),
    metadata: Optional[Dict[str, Any]] = Body(default=None),
):
    """Update task fields. Validates status transitions."""
    db = _get_db()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    current = _row_to_dict(row)
    updates: dict = {}
    now = _now()

    if priority is not None:
        updates["priority"] = priority
    if agent_id is not None:
        updates["agent_id"] = agent_id
    if result is not None:
        updates["result"] = result
    if error is not None:
        updates["error"] = error
    if metadata is not None:
        updates["metadata"] = json.dumps(metadata)

    # Status transition with validation
    if status is not None:
        if status not in VALID_STATUSES:
            db.close()
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        allowed = ALLOWED_TRANSITIONS.get(current["status"], set())
        if status not in allowed and status != current["status"]:
            db.close()
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from '{current['status']}' to '{status}'",
            )
        updates["status"] = status
        if status == "completed":
            updates["completed_at"] = now
            if current.get("started_at"):
                updates["duration_ms"] = round(
                    (datetime.fromisoformat(now) -
                     datetime.fromisoformat(current["started_at"])).total_seconds() * 1000, 2
                )
        elif status == "failed":
            updates["completed_at"] = now
            updates["retries"] = current.get("retries", 0) + 1

            # Move to dead letter if retries EXCEED max_retries (max_retries=1 = 1 retry allowed)
            if updates["retries"] > current.get("max_retries", 3):
                _move_to_dead_letter({**current, **updates},
                                     f"Max retries ({current.get('max_retries', 3)}) exceeded")
                updates["status"] = "cancelled"  # Dead letter = terminal, prevent retry
        elif status == "running" and not current.get("started_at"):
            updates["started_at"] = now

    if not updates:
        db.close()
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [task_id]
    db.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
    db.commit()

    updated = _row_to_dict(db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    db.close()
    return {"ok": True, "task": updated}


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """Delete a task (only pending/cancelled tasks)."""
    db = _get_db()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    current = _row_to_dict(row)
    if current["status"] in ("running",):
        db.close()
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete task with status '{current['status']}'",
        )

    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    db.close()
    return {"ok": True, "deleted": task_id}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a pending or running task."""
    db = _get_db()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    current = _row_to_dict(row)
    if current["status"] not in ("pending", "running"):
        db.close()
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task with status '{current['status']}'",
        )

    db.execute(
        "UPDATE tasks SET status = 'cancelled', completed_at = ? WHERE id = ?",
        (_now(), task_id),
    )
    db.commit()
    updated = _row_to_dict(db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    db.close()
    return {"ok": True, "task": updated}


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """Retry a failed task (resets to pending). Rejects dead-lettered tasks."""
    db = _get_db()
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    current = _row_to_dict(row)
    if current["status"] != "failed":
        db.close()
        raise HTTPException(
            status_code=400,
            detail=f"Can only retry failed tasks (current: '{current['status']}')",
        )

    # Check if task is in dead letter queue (permanently failed)
    dl_path = _DEAD_LETTER_DIR / f"{task_id}.json"
    if dl_path.exists():
        db.close()
        raise HTTPException(
            status_code=400,
            detail="Task is in dead letter queue (max retries exceeded). Cannot retry.",
        )

    db.execute(
        "UPDATE tasks SET status = 'pending', error = NULL, started_at = NULL, "
        "completed_at = NULL, duration_ms = NULL WHERE id = ?",
        (task_id,),
    )
    db.commit()
    updated = _row_to_dict(db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
    db.close()
    return {"ok": True, "task": updated}


# ── Filtered list endpoints ───────────────────────────────────────
@router.get("/status/pending")
async def pending_tasks(limit: int = Query(default=50, ge=1, le=500)):
    """Get pending tasks sorted by priority (highest first)."""
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM tasks WHERE status = 'pending' ORDER BY priority DESC, created_at ASC LIMIT ?",
        (limit,),
    ).fetchall()
    db.close()
    return {"ok": True, "count": len(rows), "tasks": [_row_to_dict(r) for r in rows]}


@router.get("/status/running")
async def running_tasks(limit: int = Query(default=50, ge=1, le=500)):
    """Get currently running tasks."""
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM tasks WHERE status = 'running' ORDER BY started_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    db.close()
    return {"ok": True, "count": len(rows), "tasks": [_row_to_dict(r) for r in rows]}


@router.get("/status/completed")
async def completed_tasks(limit: int = Query(default=50, ge=1, le=500)):
    """Get completed tasks (most recent first)."""
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM tasks WHERE status = 'completed' ORDER BY completed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    db.close()
    return {"ok": True, "count": len(rows), "tasks": [_row_to_dict(r) for r in rows]}


@router.get("/status/failed")
async def failed_tasks(limit: int = Query(default=50, ge=1, le=500)):
    """Get failed tasks (most recent first)."""
    db = _get_db()
    rows = db.execute(
        "SELECT * FROM tasks WHERE status = 'failed' ORDER BY completed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    db.close()
    return {"ok": True, "count": len(rows), "tasks": [_row_to_dict(r) for r in rows]}


@router.get("/status/dead-letter")
async def dead_letter_tasks(limit: int = Query(default=50, ge=1, le=500)):
    """Get permanently failed tasks from dead letter queue."""
    files = sorted(_DEAD_LETTER_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    tasks = []
    for f in files[:limit]:
        try:
            tasks.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return {"ok": True, "count": len(tasks), "tasks": tasks}


@router.get("/stats/summary")
async def task_stats():
    """Get task queue statistics."""
    db = _get_db()
    stats = {}
    for status in VALID_STATUSES:
        row = db.execute("SELECT COUNT(*) FROM tasks WHERE status = ?", (status,)).fetchone()
        stats[status] = row[0] if row else 0
    stats["dead_letter"] = len(list(_DEAD_LETTER_DIR.glob("*.json")))

    # Average duration
    avg_row = db.execute(
        "SELECT AVG(duration_ms) FROM tasks WHERE status = 'completed' AND duration_ms IS NOT NULL"
    ).fetchone()
    stats["avg_duration_ms"] = round(avg_row[0], 1) if avg_row and avg_row[0] else 0

    db.close()
    return {"ok": True, "stats": stats}
