"""
Tool wiring (Phase 6.1).

Provides a single factory for the ToolExecutor wired with Tool APIs v1.
Main/orchestrator should import get_tool_executor() and use it as the
only execution path for tools.
"""

from __future__ import annotations

from tools.executor import ToolExecutor
from tools.impl_system import system_health_check, system_get_versions, system_snapshot_capture
from tools.impl_mqtt import mqtt_publish
from tools.impl_weather import weather_tool


def get_tool_executor() -> ToolExecutor:
    impls = {
        "system.health_check": system_health_check,
        "system.get_versions": system_get_versions,
        "system.snapshot_capture": system_snapshot_capture,
        "mqtt.publish": mqtt_publish,
        "weather": weather_tool,
    }
    return ToolExecutor(impls=impls)
