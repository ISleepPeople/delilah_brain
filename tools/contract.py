"""
Tool contract types for Delilah Brain v2.

Phase 6 requirements:
- Tools executed only by centralized executor
- Every call has trace_id
- ToolResult is normalized (executor never crashes orchestration)

Agentic-ready extensions (no behavior changes yet):
- purpose, risk_level, idempotency_key, dry_run, expected_effects
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Literal
import time


RiskLevel = Literal["READ_ONLY", "MUTATING"]


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass(frozen=True)
class ToolRequest:
    trace_id: str
    tool_name: str
    args: Dict[str, Any] = field(default_factory=dict)

    # Agentic-ready extensions (compatible; may be None in Phase 6)
    purpose: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    idempotency_key: Optional[str] = None
    dry_run: Optional[bool] = None
    expected_effects: Optional[str] = None

    requested_at_ms: int = field(default_factory=now_ms)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "tool_name": self.tool_name,
            "args": self.args,
            "purpose": self.purpose,
            "risk_level": self.risk_level,
            "idempotency_key": self.idempotency_key,
            "dry_run": self.dry_run,
            "expected_effects": self.expected_effects,
            "requested_at_ms": self.requested_at_ms,
        }


@dataclass(frozen=True)
class ToolResult:
    trace_id: str
    tool_name: str
    ok: bool

    # Normalized payload
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # Timing
    started_at_ms: int = field(default_factory=now_ms)
    finished_at_ms: int = field(default_factory=now_ms)
    duration_ms: int = 0

    # Optional structured audit metadata (Phase 6.6 will persist these)
    audit: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "tool_name": self.tool_name,
            "ok": self.ok,
            "result": self.result,
            "error": self.error,
            "started_at_ms": self.started_at_ms,
            "finished_at_ms": self.finished_at_ms,
            "duration_ms": self.duration_ms,
            "audit": self.audit,
        }


def ok_result(*, trace_id: str, tool_name: str, result: Dict[str, Any], started_at_ms: int) -> ToolResult:
    finished = now_ms()
    return ToolResult(
        trace_id=trace_id,
        tool_name=tool_name,
        ok=True,
        result=result,
        error=None,
        started_at_ms=started_at_ms,
        finished_at_ms=finished,
        duration_ms=max(0, finished - started_at_ms),
    )


def error_result(*, trace_id: str, tool_name: str, error: str, started_at_ms: int) -> ToolResult:
    finished = now_ms()
    return ToolResult(
        trace_id=trace_id,
        tool_name=tool_name,
        ok=False,
        result=None,
        error=error,
        started_at_ms=started_at_ms,
        finished_at_ms=finished,
        duration_ms=max(0, finished - started_at_ms),
    )
