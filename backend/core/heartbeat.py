"""
backend/core/heartbeat.py — ENHANCED HEARTBEAT PROTOCOL
========================================================
Rich per-agent heartbeat system worthy of an operating system.

A heartbeat doesn't only mean "I'm alive." It answers:
  - What are you thinking about?
  - Are you making progress?
  - Are you blocked?
  - Are you hallucinating?
  - How full is your context?
  - How long have you been idle?
  - What tools are currently running?
  - What file are you touching?
  - What task owns you?
  - Can you safely accept another task?

Every agent broadcasts this on a 1-5 second interval.
The Kernel/Princess/Auditor all consume this single stream.

Usage:
  from backend.core.heartbeat import HeartbeatProtocol, Heartbeat
  hb = Heartbeat(
      agent_id="claude-01",
      state="thinking",
      current_task="Implement auth",
      context_fullness_pct=72.5,
  )
  protocol.record(hb)
  protocol.broadcast(hb)  # publishes to unified event bus
"""

from __future__ import annotations

import time
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path


class HeartbeatState(str, Enum):
    """Fine-grained agent sub-states for heartbeat reporting."""
    IDLE = "idle"
    THINKING = "thinking"
    REASONING = "reasoning"           # Deep chain-of-thought
    CALLING_TOOL = "calling_tool"     # Awaiting tool result
    WAITING_USER = "waiting_user"     # Waiting for human input
    GENERATING = "generating"         # Producing output
    BLOCKED_ON_IO = "blocked_on_io"   # File/network I/O
    BLOCKED_ON_AGENT = "blocked_on_agent"  # Waiting for another agent
    ERROR_RECOVERY = "error_recovery" # Attempting self-repair
    COMPRESSING = "compressing"       # Compacting context
    TERMINATING = "terminating"       # Shutting down


class HallucinationRisk(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Heartbeat:
    """A single heartbeat from an agent.
    
    This is the canonical heartbeat shape. Every agent MUST broadcast
    this on their configured interval. The Kernel validates presence;
    Princess narrates changes; Auditor checks integrity.
    """
    # ── Identity ──
    agent_id: str                                    # Unique agent identifier
    agent_type: str = ""                             # claude, gemini, hermes, etc.
    sap_version: str = "1.0"                         # Protocol version
    sequence_number: int = 0                         # Monotonically increasing
    
    # ── State ──
    state: str = "idle"                              # HeartbeatState value
    accepting_tasks: bool = True                     # Can this agent take new work?
    
    # ── Current Work ──
    current_task: Optional[str] = None               # Description of current task
    sub_task: Optional[str] = None                   # Current sub-step
    task_id: Optional[str] = None                    # System task identifier
    files_touching: List[str] = field(default_factory=list)  # Files being edited
    tools_running: List[str] = field(default_factory=list)   # Active tool calls
    
    # ── Context Health ──
    context_fullness_pct: float = 0.0                # 0-100, how full is context window
    context_tokens_used: int = 0                     # Approximate token count
    context_tokens_max: int = 200000                 # Provider's context limit
    context_age_s: float = 0.0                       # Seconds since last context compression
    context_compressions: int = 0                    # Total compressions this session
    
    # ── Reasoning Health ──
    reasoning_chain_depth: int = 0                   # How deep is current CoT
    hallucination_risk: str = "none"                 # HallucinationRisk value
    objective_drift_score: float = 0.0               # 0-1, similarity to original task
    response_relevance_score: float = 1.0            # 0-1, similarity to last user msg
    loop_detection_count: int = 0                    # Repeated output patterns
    
    # ── Performance ──
    memory_usage_mb: float = 0.0
    cpu_percent: float = 0.0
    gpu_percent: float = 0.0
    last_user_message_age_s: float = 0.0             # Seconds since last human interaction
    last_tool_call_age_s: float = 0.0                # Seconds since last tool use
    idle_duration_s: float = 0.0                     # Seconds since last productive output
    
    # ── Reliability ──
    retry_count: int = 0
    error_count_1h: int = 0
    crash_count: int = 0
    uptime_s: float = 0.0
    
    # ── Blocking Info ──
    blocked_by: Optional[str] = None                 # What's blocking this agent
    blocked_since_s: float = 0.0                     # How long blocked
    
    # ── Metadata ──
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON/broadcast."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Heartbeat":
        """Deserialize from dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class HeartbeatSummary:
    """Aggregated view of all agent heartbeats for the dashboard."""
    total_agents: int = 0
    agents_by_state: Dict[str, int] = field(default_factory=dict)
    agents_by_type: Dict[str, int] = field(default_factory=dict)
    avg_context_fullness: float = 0.0
    agents_near_overflow: int = 0             # context > 80%
    agents_stalled: int = 0                   # no heartbeat in 30s
    agents_hallucinating: int = 0             # hallucination risk >= medium
    agents_in_loop: int = 0                   # loop_detection_count > 3
    total_errors_1h: int = 0
    avg_cpu_percent: float = 0.0
    total_memory_mb: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HeartbeatProtocol:
    """Manages heartbeat recording, broadcasting, and analysis.
    
    This is the SINGLE place where heartbeats flow through.
    Every agent writes here; every consumer reads from here.
    """
    
    def __init__(self, max_history: int = 5000) -> None:
        self._heartbeats: Dict[str, List[Heartbeat]] = {}  # agent_id → history
        self._latest: Dict[str, Heartbeat] = {}             # agent_id → latest
        self._max_history = max_history
        self._subscribers: List[Callable] = []              # (agent_id, Heartbeat) -> None
        self._alert_subscribers: List[Callable] = []        # (alert_type, agent_id, message) -> None
    
    # ── Recording ──────────────────────────────────────────────────
    
    def record(self, heartbeat: Heartbeat) -> None:
        """Record a heartbeat from an agent."""
        agent_id = heartbeat.agent_id
        
        # Store in history
        if agent_id not in self._heartbeats:
            self._heartbeats[agent_id] = []
        self._heartbeats[agent_id].append(heartbeat)
        
        # Prune old entries
        history = self._heartbeats[agent_id]
        if len(history) > self._max_history:
            self._heartbeats[agent_id] = history[-self._max_history:]
        
        # Update latest
        self._latest[agent_id] = heartbeat
        
        # Check for alert conditions
        self._check_alerts(agent_id, heartbeat)
    
    async def broadcast(self, heartbeat: Heartbeat) -> None:
        """Record + broadcast to all subscribers + publish to event bus."""
        self.record(heartbeat)
        
        # Notify local subscribers (handles both sync and async callbacks)
        import asyncio as _asyncio
        for callback in self._subscribers:
            try:
                if _asyncio.iscoroutinefunction(callback):
                    await callback(heartbeat.agent_id, heartbeat)
                else:
                    callback(heartbeat.agent_id, heartbeat)
            except Exception:
                pass
        
        # Publish to unified event bus
        try:
            from backend.core.unified_event_bus import publish, EcosystemEvent as EcoEvt
            publish(EcoEvt.AGENT_HEARTBEAT, heartbeat.to_dict(), source="heartbeat_protocol")
        except ImportError:
            pass
    
    # ── Querying ───────────────────────────────────────────────────
    
    def get_latest(self, agent_id: str) -> Optional[Heartbeat]:
        """Get the most recent heartbeat for an agent."""
        return self._latest.get(agent_id)
    
    def get_all_latest(self) -> Dict[str, Heartbeat]:
        """Get latest heartbeat for all agents."""
        return dict(self._latest)
    
    def get_history(self, agent_id: str, limit: int = 100) -> List[Heartbeat]:
        """Get heartbeat history for an agent."""
        history = self._heartbeats.get(agent_id, [])
        return history[-limit:] if limit else history
    
    def is_agent_alive(self, agent_id: str, max_age_s: float = 30.0) -> bool:
        """Check if an agent has sent a heartbeat recently."""
        hb = self._latest.get(agent_id)
        if not hb:
            return False
        return (time.time() - hb.timestamp) < max_age_s
    
    def get_stale_agents(self, max_age_s: float = 30.0) -> List[str]:
        """Get agents that haven't heartbeated recently."""
        now = time.time()
        return [
            agent_id for agent_id, hb in self._latest.items()
            if (now - hb.timestamp) >= max_age_s
        ]
    
    # ── Analysis / Summary ─────────────────────────────────────────
    
    def summarize(self) -> HeartbeatSummary:
        """Produce a dashboard-ready summary of all agent heartbeats."""
        latest = self._latest
        if not latest:
            return HeartbeatSummary()
        
        states: Dict[str, int] = {}
        types_: Dict[str, int] = {}
        fullness_sum = 0.0
        near_overflow = 0
        stalled = 0
        hallucinating = 0
        looping = 0
        errors = 0
        cpu_sum = 0.0
        mem_sum = 0.0
        now = time.time()
        
        for agent_id, hb in latest.items():
            # State counts
            state = hb.state or "unknown"
            states[state] = states.get(state, 0) + 1
            
            # Type counts
            atype = hb.agent_type or "unknown"
            types_[atype] = types_.get(atype, 0) + 1
            
            # Averages
            fullness_sum += hb.context_fullness_pct
            cpu_sum += hb.cpu_percent
            mem_sum += hb.memory_usage_mb
            errors += hb.error_count_1h
            
            # Flags
            if hb.context_fullness_pct > 80:
                near_overflow += 1
            if (now - hb.timestamp) > 30:
                stalled += 1
            if hb.hallucination_risk in (HallucinationRisk.MEDIUM.value, 
                                          HallucinationRisk.HIGH.value,
                                          HallucinationRisk.CRITICAL.value):
                hallucinating += 1
            if hb.loop_detection_count > 3:
                looping += 1
        
        n = len(latest)
        return HeartbeatSummary(
            total_agents=n,
            agents_by_state=states,
            agents_by_type=types_,
            avg_context_fullness=round(fullness_sum / n, 1) if n else 0,
            agents_near_overflow=near_overflow,
            agents_stalled=stalled,
            agents_hallucinating=hallucinating,
            agents_in_loop=looping,
            total_errors_1h=errors,
            avg_cpu_percent=round(cpu_sum / n, 1) if n else 0,
            total_memory_mb=round(mem_sum, 1),
        )
    
    # ── Alerts ─────────────────────────────────────────────────────
    
    def _check_alerts(self, agent_id: str, hb: Heartbeat) -> None:
        """Check for alert conditions on a new heartbeat."""
        alerts = []
        
        # Context overflow warning
        if hb.context_fullness_pct > 85:
            alerts.append(("context_near_overflow", f"{agent_id} context at {hb.context_fullness_pct:.0f}%"))
        
        # Hallucination risk
        if hb.hallucination_risk in (HallucinationRisk.HIGH.value, HallucinationRisk.CRITICAL.value):
            alerts.append(("hallucination_risk", f"{agent_id} hallucination risk: {hb.hallucination_risk}"))
        
        # Loop detection
        if hb.loop_detection_count > 5:
            alerts.append(("loop_detected", f"{agent_id} repeated output {hb.loop_detection_count} times"))
        
        # Objective drift
        if hb.objective_drift_score > 0.5:
            alerts.append(("objective_drift", f"{agent_id} drifted from objective (score={hb.objective_drift_score:.2f})"))
        
        # Blocked too long
        if hb.state == "blocked" and hb.blocked_since_s > 120:
            alerts.append(("agent_stuck", f"{agent_id} blocked for {hb.blocked_since_s:.0f}s: {hb.blocked_by}"))
        
        for alert_type, message in alerts:
            for callback in self._alert_subscribers:
                try:
                    callback(alert_type, agent_id, message)
                except Exception:
                    pass
    
    def on_alert(self, callback: Callable) -> None:
        """Subscribe to heartbeat alerts."""
        self._alert_subscribers.append(callback)
    
    def subscribe(self, callback: Callable) -> None:
        """Subscribe to all heartbeats."""
        self._subscribers.append(callback)


# ══════════════════════════════════════════════════════════════════════
# SINGLETON
# ══════════════════════════════════════════════════════════════════════

heartbeat_protocol = HeartbeatProtocol()
