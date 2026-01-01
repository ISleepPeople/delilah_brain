# -*- coding: utf-8 -*-
"""
Central Policy Module (Phase 6.0)

Goals:
- Deterministic, testable decisions (no implicit magic)
- Enforce invariants (e.g., tool intent bypasses RAG; volatile never writes back)
- Provide typed envelopes for orchestrator/tool/fallback layers
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
import re


# ============================
# Types
# ============================

class Intent(str, Enum):
    TOOL = "tool"
    KNOWLEDGE = "knowledge"
    MIXED = "mixed"


class Volatility(str, Enum):
    STABLE = "stable"
    VOLATILE = "volatile"


@dataclass(frozen=True)
class RedactionReport:
    redacted: bool
    patterns: List[str]
    notes: str = ""


@dataclass(frozen=True)
class RoutingPlan:
    intent: Intent
    volatility: Volatility
    expert_id: str  # "general" | "coding" | future experts
    tool_name: Optional[str] = None


@dataclass(frozen=True)
class RetrievalPlan:
    use_rag: bool
    allowed_collections: List[str]
    top_k: int = 3


@dataclass(frozen=True)
class FallbackDecision:
    allowed: bool
    reason_codes: List[str]


@dataclass(frozen=True)
class WritebackDecision:
    allowed: bool
    reason_codes: List[str]


# ============================
# Deterministic classifiers (v0)
# ============================

_WEATHER_WORDS = ("weather", "forecast", "temperature", "rain", "snow", "wind")
_TIME_VOLATILE_WORDS = ("today", "tonight", "right now", "current", "latest", "score", "prices", "stock", "stocks")

# Tool name classifier (Tool APIs v1)
# Note: we keep this deterministic and conservative to avoid side-effects.
def classify_tool_name(text: str) -> Optional[str]:
    t = (text or "").lower()

    # Weather tool
    if any(w in t for w in _WEATHER_WORDS):
        return "weather"

    # System tools
    # - "health check" / "status" => system.health_check
    # - "versions" / "what versions" => system.get_versions
    if any(p in t for p in ["health check", "healthcheck", "system status", "service status", "status check", "uptime"]):
        return "system.health_check"
    if any(p in t for p in ["what version", "versions", "version info", "build info", "what are you running"]):
        return "system.get_versions"

    # MQTT publish tool (only if user explicitly mentions topic to avoid unintended publishes)
    if "mqtt" in t and ("topic " in t or "topic:" in t):
        return "mqtt.publish"
    if "publish" in t and ("topic " in t or "topic:" in t):
        return "mqtt.publish"

    return None


def classify_intent(text: str) -> Intent:
    # Tool intent iff we can deterministically name the tool.
    return Intent.TOOL if classify_tool_name(text) else Intent.KNOWLEDGE


def classify_volatility(text: str) -> Volatility:
    t = (text or "").lower()
    # Any tool intent is treated as volatile (no writeback).
    if classify_tool_name(text):
        return Volatility.VOLATILE
    if any(w in t for w in _TIME_VOLATILE_WORDS):
        return Volatility.VOLATILE
    return Volatility.STABLE


# ============================
# Redaction (deterministic, minimal v0)
# ============================

_RE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("api_key_like", re.compile(r"\b(sk-[A-Za-z0-9]{16,}|AIza[0-9A-Za-z\-_]{20,})\b")),
]


def redact_for_cloud(text: str) -> Tuple[str, RedactionReport]:
    src = text or ""
    redacted = src
    hits: List[str] = []

    for name, pat in _RE_PATTERNS:
        if pat.search(redacted):
            hits.append(name)
            redacted = pat.sub("[REDACTED]", redacted)

    return redacted, RedactionReport(redacted=(redacted != src), patterns=hits)


# ============================
# Policy decisions (Phase 6.0 contract)
# ============================

def decide_routing(text: str) -> RoutingPlan:
    intent = classify_intent(text)
    vol = classify_volatility(text)

    if intent == Intent.TOOL:
        tool = classify_tool_name(text)
        if not tool:
            # Defensive: should not happen because classify_intent depends on tool_name.
            return RoutingPlan(intent=Intent.KNOWLEDGE, volatility=vol, expert_id="general", tool_name=None)
        return RoutingPlan(intent=intent, volatility=vol, expert_id="general", tool_name=tool)

    return RoutingPlan(intent=intent, volatility=vol, expert_id="general", tool_name=None)


def decide_retrieval(*, routing: RoutingPlan, default_collections: Optional[List[str]] = None) -> RetrievalPlan:
    """
    Invariant: tool intent => no RAG.
    """
    default_collections = default_collections or ["delilah_knowledge_v768"]

    if routing.intent == Intent.TOOL:
        return RetrievalPlan(use_rag=False, allowed_collections=[], top_k=0)

    return RetrievalPlan(use_rag=True, allowed_collections=list(default_collections), top_k=3)


def decide_fallback(*, routing: RoutingPlan, redaction_report: RedactionReport, local_sufficient: bool) -> FallbackDecision:
    """
    v0 gating:
    - No fallback for tool intents
    - Only allowed if local is not sufficient
    """
    if routing.intent == Intent.TOOL:
        return FallbackDecision(allowed=False, reason_codes=["intent_tool"])

    if local_sufficient:
        return FallbackDecision(allowed=False, reason_codes=["local_sufficient"])

    return FallbackDecision(allowed=True, reason_codes=["local_insufficient"])


def decide_writeback(*, routing: RoutingPlan, consensus_ok: bool) -> WritebackDecision:
    """
    Invariant: volatile => never write back.
    """
    if routing.volatility == Volatility.VOLATILE:
        return WritebackDecision(allowed=False, reason_codes=["volatile"])

    if not consensus_ok:
        return WritebackDecision(allowed=False, reason_codes=["no_consensus"])

    return WritebackDecision(allowed=True, reason_codes=["stable_consensus"])
