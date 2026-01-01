"""
Central tool executor (Phase 6.1).

Responsibilities:
- Allowlist enforcement (registry)
- Soft arg validation (registry)
- Normalized ToolResult envelopes (never throw upstream)
- Basic timing + audit metadata
- Executes tool implementations (Phase 6.1 Tool APIs v1)

Note: policy gating is introduced later (Phase 6.0/6.1 guardrails),
but this executor is the single choke point that policy will wrap.
"""

from __future__ import annotations

from typing import Any, Dict, Callable

from tools.contract import ToolRequest, ToolResult, ok_result, error_result, now_ms
from tools.registry import is_tool_allowed, get_tool_spec, soft_validate_args


ToolImpl = Callable[[Dict[str, Any]], Dict[str, Any]]


class ToolExecutor:
    def __init__(self, impls: Dict[str, ToolImpl]):
        self.impls = impls

    def execute(self, req: ToolRequest) -> ToolResult:
        started = now_ms()

        # Allowlist
        if not is_tool_allowed(req.tool_name):
            return error_result(
                trace_id=req.trace_id,
                tool_name=req.tool_name,
                error=f"Tool not allowed: {req.tool_name}",
                started_at_ms=started,
            )

        # Implementation present
        impl = self.impls.get(req.tool_name)
        if impl is None:
            return error_result(
                trace_id=req.trace_id,
                tool_name=req.tool_name,
                error=f"No implementation registered for tool: {req.tool_name}",
                started_at_ms=started,
            )

        # Soft arg validation
        warn = soft_validate_args(req.tool_name, req.args)
        if warn:
            # Treat missing required args as hard error; unexpected args as soft warning.
            # soft_validate_args currently returns one string; we classify by prefix.
            if warn.startswith("Missing required arg"):
                return error_result(
                    trace_id=req.trace_id,
                    tool_name=req.tool_name,
                    error=warn,
                    started_at_ms=started,
                )

        try:
            out = impl(req.args or {})
            spec = get_tool_spec(req.tool_name)

            audit = {
                "tool_name": req.tool_name,
                "risk_level": getattr(spec, "risk_level", None),
                "purpose": req.purpose,
                "idempotency_key": req.idempotency_key,
                "dry_run": req.dry_run,
                "expected_effects": req.expected_effects,
                "arg_warning": warn,
            }
            # Propagate semantic ok/error from tool payload when present.

            semantic_ok = True

            semantic_err = None

            if isinstance(out, dict) and "ok" in out:

                semantic_ok = bool(out.get("ok"))

                if not semantic_ok:

                    semantic_err = out.get("error") or "tool returned ok=false"


            if semantic_ok:

                res = ok_result(

                    trace_id=req.trace_id,

                    tool_name=req.tool_name,

                    result=out or {},

                    started_at_ms=started,

                )

            else:

                # Use error_result for timestamps/duration, but preserve tool payload in result.

                _tmp = error_result(

                    trace_id=req.trace_id,

                    tool_name=req.tool_name,

                    error=str(semantic_err),

                    started_at_ms=started,

                )

                res = ToolResult(

                    trace_id=_tmp.trace_id,

                    tool_name=_tmp.tool_name,

                    ok=_tmp.ok,

                    result=out if isinstance(out, dict) else {"value": out},

                    error=_tmp.error,

                    started_at_ms=_tmp.started_at_ms,

                    finished_at_ms=_tmp.finished_at_ms,

                    duration_ms=_tmp.duration_ms,

                    audit=None,

                )

            # attach audit without mutating frozen dataclass: create a new ToolResult# attach audit without mutating frozen dataclass: create a new ToolResult
            return ToolResult(
                trace_id=res.trace_id,
                tool_name=res.tool_name,
                ok=res.ok,
                result=res.result,
                error=res.error,
                started_at_ms=res.started_at_ms,
                finished_at_ms=res.finished_at_ms,
                duration_ms=res.duration_ms,
                audit=audit,
            )

        except Exception as e:
            return error_result(
                trace_id=req.trace_id,
                tool_name=req.tool_name,
                error=str(e),
                started_at_ms=started,
            )
