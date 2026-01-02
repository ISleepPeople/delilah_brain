# -*- coding: utf-8 -*-

from policy.policy import (
    decide_routing,
    decide_retrieval,
    decide_writeback,
    redact_for_cloud,
    Intent,
    Volatility,
)

def test_tool_intent_bypasses_rag():
    routing = decide_routing("What is the weather in Rockford, MI?")
    assert routing.intent == Intent.TOOL
    rp = decide_retrieval(routing=routing, default_collections=["anything"])
    assert rp.use_rag is False
    assert rp.allowed_collections == []
    assert rp.top_k == 0

def test_volatile_never_writes_back():
    routing = decide_routing("What is the weather today?")
    assert routing.volatility == Volatility.VOLATILE
    wd = decide_writeback(routing=routing, consensus_ok=True)
    assert wd.allowed is False
    assert "volatile" in wd.reason_codes

def test_redaction_runs_and_masks_common_patterns():
    redacted, report = redact_for_cloud("Email me at test@example.com and my IP is 192.168.1.111")
    assert "[REDACTED]" in redacted
    assert report.redacted is True
    assert ("email" in report.patterns) or ("ipv4" in report.patterns)

def test_weather_shorthand_classifies_weather():
    # Shorthand that previously fell through routing
    from policy.policy import classify_tool_name
    assert classify_tool_name("weather San Juan, PR") == "weather"


def test_mqtt_publish_classifies_mqtt_publish():
    # Guard against false-positive weather routing: "brain" contains "rain"
    from policy.policy import classify_tool_name
    assert classify_tool_name("mqtt publish topic: delilah/test payload: hello-from-env-brain") == "mqtt.publish"

