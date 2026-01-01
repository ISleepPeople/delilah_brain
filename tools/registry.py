"""
Tool registry (Phase 6.1).

Defines:
- canonical tool names
- risk level (READ_ONLY vs MUTATING)
- minimal arg schema (soft validation)
- allowlist surface for executor

Note: This is intentionally lightweight; stricter schema validation can be added later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Literal


RiskLevel = Literal["READ_ONLY", "MUTATING"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    risk_level: RiskLevel
    description: str
    # Minimal arg hints (soft validation)
    required_args: Optional[tuple[str, ...]] = None
    optional_args: Optional[tuple[str, ...]] = None


# Phase 6.1 Tool APIs v1 (from runbook)
TOOL_SPECS: Dict[str, ToolSpec] = {
    "system.health_check": ToolSpec(
        name="system.health_check",
        risk_level="READ_ONLY",
        description="Return health status for core services (brain, qdrant, postgres, n8n).",
        required_args=(),
        optional_args=(),
    ),
    "system.get_versions": ToolSpec(
        name="system.get_versions",
        risk_level="READ_ONLY",
        description="Return versions for key components (python, app, qdrant, postgres, etc.).",
        required_args=(),
        optional_args=(),
    ),
    "system.snapshot_capture": ToolSpec(
        name="system.snapshot_capture",
        risk_level="READ_ONLY",
        description="Capture a small but comprehensive snapshot (compose, env, versions) per runbook.",
        required_args=(),
        optional_args=("label",),
    ),
    "mqtt.publish": ToolSpec(
        name="mqtt.publish",
        risk_level="MUTATING",
        description="Publish an MQTT message to a topic (used for HA/OVOS integration).",
        required_args=("topic", "payload"),
        optional_args=("qos", "retain"),
    ),

    "weather": ToolSpec(
        name="weather",
        risk_level="READ_ONLY",
        description="Real-time weather lookup using weather.gov.",
        required_args=(),
        optional_args=("location", "location_name"),
    ),
}


def get_tool_spec(tool_name: str) -> Optional[ToolSpec]:
    return TOOL_SPECS.get(tool_name)


def is_tool_allowed(tool_name: str) -> bool:
    return tool_name in TOOL_SPECS


def soft_validate_args(tool_name: str, args: Dict[str, Any]) -> Optional[str]:
    spec = get_tool_spec(tool_name)
    if not spec:
        return f"Unknown tool: {tool_name}"

    args = args or {}
    required = spec.required_args or ()
    for k in required:
        if k not in args:
            return f"Missing required arg: {k}"

    # If optional_args is provided, warn if unexpected keys appear (soft)
    allowed = set(required) | set(spec.optional_args or ())
    unexpected = [k for k in args.keys() if k not in allowed]
    if unexpected:
        return f"Unexpected args: {unexpected}"

    return None
