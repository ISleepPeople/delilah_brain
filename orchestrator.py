# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict, List, Tuple
from datetime import datetime, timezone
import os
import re


from policy.policy import decide_routing, decide_retrieval
from tools.contract import ToolRequest
from tools.wiring import get_tool_executor

try:
    from pg_logger import log_tool_call
except Exception:
    def log_tool_call(*args, **kwargs):
        return
# Tools that must never be persisted (tool_calls) and must not use RAG context
EPHEMERAL_TOOLS = {"weather", "sports", "stocks"}



# ============================
# STATE MODEL
# ============================

class BrainState(TypedDict, total=False):
    text: str
    user_id: str
    trace_id: str
    context: str
    used_context: bool
    num_docs: int
    used_conversation_context: bool
    conversation_context: str
    target_expert: str
    answer: str
    tool: Optional[str]
    tool_args: Dict[str, Any]
    tool_result: Any
    tool_error: Optional[str]


# ============================
# SMALL UTILS
# ============================

def clamp_text(s: str, max_chars: int = 2500) -> str:
    s = (s or "").strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 20] + "\n...[truncated]..."


# ============================
# POLICY B  CONVERSATION MEMORY
# ============================

_CONVO_HINT_PATTERNS = [
    r"\bremember\b",
    r"\byou said\b",
    r"\blast time\b",
    r"\bearlier\b",
    r"\bprevious(ly)?\b",
    r"\bwe talked\b",
    r"\bwhat did i say\b",
    r"\bmy favorite\b",
    r"\bmy preference\b",
    r"\bfrom now on\b",
    r"\bgoing forward\b",
    r"\bdon't forget\b",
]

def conversation_relevance_heuristic(query: str) -> bool:
    q = (query or "").lower()
    if not q:
        return False
    if any(re.search(p, q) for p in _CONVO_HINT_PATTERNS):
        return True
    if len(q) <= 18 and any(w in q for w in ["favorite", "prefer", "like", "hate"]):
        return True
    return False


def retrieve_conversation_context_if_relevant(
    *,
    conv_store,
    user_id: str,
    query_text: str,
    k: int = 6,
) -> Tuple[str, bool]:
    """
    IMPORTANT:
    We intentionally do NOT apply score thresholds here because score semantics differ across
    distance metrics and client versions. We rely on top-k ordering.
    """
    if not conversation_relevance_heuristic(query_text):
        return "", False
    try:
        q = f"user_id={user_id}\n{query_text}"
        rows = conv_store.similarity_search_with_score(q, k=k)
        kept: List[str] = []
        for d, _score in rows:
            if getattr(d, "page_content", ""):
                kept.append(d.page_content)
        if not kept:
            return "", False
        return clamp_text("\n---\n".join(kept)), True
    except Exception as e:
        print(f"[Delilah Brain] conversation_memory warning: {e}", flush=True)
        return "", False


# ============================
# ROUTER HINTS
# ============================

def router_hint_target(*, router_store, user_id: str, query_text: str) -> str:
    try:
        q = f"user_id={user_id}\n{query_text}"
        docs = router_store.similarity_search(q, k=3)
        for d in docs:
            meta = getattr(d, "metadata", {}) or {}
            if meta.get("target_expert"):
                return str(meta["target_expert"])
    except Exception as e:
        print(f"[Delilah Brain] router_hints warning: {e}", flush=True)
    return "general"


# ============================
# PERSONA MEMORY
# ============================

def persona_directives(*, persona_store, user_id: str, k: int = 4) -> str:
    try:
        q = f"user_id={user_id}\npersona directives"
        docs = persona_store.similarity_search(q, k=k)
        lines = [d.page_content.strip() for d in docs if getattr(d, "page_content", "").strip()]
        return clamp_text("\n".join(lines), 1200) if lines else ""
    except Exception as e:
        print(f"[Delilah Brain] persona_memory warning: {e}", flush=True)
        return ""


# ============================
# WEATHER TOOL
# ============================

DEFAULT_LOCATION_QUERY = "Rockford, MI 49341"

def weather_tool(tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Real-time weather lookup using weather.gov.
    Policy:
      - No RAG context
      - No persistence to Postgres
      - No memory writes
    """
    import requests
    import time

    location_query = (
        tool_args.get("location")
        or tool_args.get("location_name")
        or DEFAULT_LOCATION_QUERY
    )

    # Use a descriptive User-Agent and accept both geo+json and json.
    headers = {
        "User-Agent": "Delilah/1.0 (contact: local)",
        "Accept": "application/geo+json, application/json;q=0.9, */*;q=0.1",
    }

    session = requests.Session()
    session.headers.update(headers)

    def _get_json(url: str, *, params: Dict[str, Any] | None = None, timeout: int = 15, retries: int = 2) -> Any:
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                resp = session.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(0.8)
        raise last_err  # type: ignore[misc]

    try:
        # 1) Resolve location to lat/lon (Nominatim)
        geo = _get_json(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location_query, "format": "json", "limit": 1},
            timeout=15,
            retries=2,
        )

        if not geo:
            return {
                "ok": False,
                "error": f"Could not resolve location '{location_query}'",
                "source": "weather.gov",
            }

        lat = geo[0]["lat"]
        lon = geo[0]["lon"]

        # 2) Get weather.gov grid endpoint
        points = _get_json(
            f"https://api.weather.gov/points/{lat},{lon}",
            timeout=15,
            retries=2,
        )

        forecast_url = points["properties"]["forecast"]

        # 3) Get forecast
        forecast = _get_json(
            forecast_url,
            timeout=15,
            retries=2,
        )

        periods = forecast["properties"]["periods"]
        if not periods:
            return {
                "ok": False,
                "error": "Weather forecast unavailable",
                "source": "weather.gov",
            }

        now = periods[0]
        summary = (
            f"{now['name']}: {now['temperature']} {now['temperatureUnit']}, "
            f"{now['shortForecast']}."
        )

        return {
            "ok": True,
            "location": location_query,
            "summary": summary,
            "source": "weather.gov",
            "used_context": False,
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "source": "weather.gov",
        }

def detect_weather_intent(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in ["weather", "forecast", "temperature", "rain", "snow", "wind"])

def parse_weather_args(query_text: str) -> Dict[str, Any]:
    """Extract a location from common weather/forecast phrasings.
    Returns {} if no location is confidently found (caller may fall back).
    Supports:
      - "weather in <location>" / "forecast for <location>"
      - "weather <location>" / "forecast <location>" (common shorthand)
    """
    t = (query_text or "").strip()
    if not t:
        return {}

    # Prefer matching 'weather/forecast ... in/for <location>'
    rx = re.compile(
        r"\b(?:weather|forecast)\b"
        r"(?:\s+(?:today|tonight|tomorrow|right\s+now|this\s+week|this\s+weekend))?"
        r"\s+(?:in|for)\s+(?P<loc>.+?)"
        r"(?:[\?\.!]\s*|\s*$)",
        flags=re.IGNORECASE,
    )
    m = rx.search(t)

    # Secondary fallback: allow 'in/for <location>' even without the word 'weather'
    if not m:
        rx2 = re.compile(
            r"\b(?:in|for)\s+(?P<loc>[^\?\.!]+?)(?:[\?\.!]\s*|\s*$)",
            flags=re.IGNORECASE,
        )
        m = rx2.search(t)

    # Tertiary fallback: "weather <location>" / "forecast <location>" / "temperature <location>"
    if not m:
        rx3 = re.compile(
            r"^\s*(?:what\s*\'?s\s+the\s+)?(?:weather|forecast|temperature)\b\s*[:\-]?\s+(?P<loc>.+?)\s*$",
            flags=re.IGNORECASE,
        )
        m = rx3.search(t)
        if not m:
            return {}

        candidate = (m.group("loc") or "").strip()
        # Avoid false positives like "weather tomorrow"
        cand_l = candidate.lower().strip()
        temporal = [
            "today", "tonight", "tomorrow", "right now", "now",
            "this week", "this weekend", "later", "next week",
        ]
        if any(cand_l == x or cand_l.startswith(x + " ") for x in temporal):
            return {}

    loc = (m.group("loc") or "").strip()
    loc = re.sub(r"\s+(?:please|thanks|thank\s+you)\s*$", "", loc, flags=re.IGNORECASE).strip()
    loc = loc.strip(" \"'")

    return {"location": loc}


# ============================
# GRAPH
# ============================

def build_simple_graph(*, llm, vector_store, conv_store, persona_store, router_store):
    executor = get_tool_executor()
    class _Graph:
        def invoke(self, state: BrainState) -> BrainState:
            text = (state.get("text") or "").strip()
            user_id = (state.get("user_id") or "ryan").strip() or "ryan"

            # Phase 6.0 policy (deterministic routing + retrieval invariants)
            policy_routing = decide_routing(text)
            policy_retrieval = decide_retrieval(routing=policy_routing, default_collections=[])

            state["policy"] = {
                "intent": policy_routing.intent.value,
                "volatility": policy_routing.volatility.value,
                "expert_id": policy_routing.expert_id,
                "tool_name": policy_routing.tool_name,
                "use_rag": policy_retrieval.use_rag,
                "top_k": policy_retrieval.top_k,
            }

            state.update({
                "tool": None,
                "tool_args": {},
                "tool_result": None,
                "tool_error": None,
            })

            
            # Phase 6.0 invariant: tool-intent bypasses RAG (force tool early)
            if state.get("policy", {}).get("intent") == "tool" and state.get("policy", {}).get("tool_name"):
                state["tool"] = state.get("policy", {}).get("tool_name")
# Router hints
            state["target_expert"] = router_hint_target(
                router_store=router_store,
                user_id=user_id,
                query_text=text,
            )

            # Persona
            persona = persona_directives(persona_store=persona_store, user_id=user_id)

            # Determine if this is a policy tool intent (Tool APIs v1) or a heuristic weather intent (legacy)
            policy_tool = state.get("policy", {}).get("tool_name")
            is_tool_intent = (state.get("policy", {}).get("intent") == "tool") and bool(policy_tool)
            # Weather can still be triggered heuristically, but policy tool-intent always bypasses RAG.
            is_weather = ((state.get("tool") or policy_tool) == "weather") or detect_weather_intent(text)

            # Always initialize locals so later code cannot reference undefined names
            convo_ctx = ""
            used_convo = False
            docs: List[Any] = []
            rag_ctx = ""

            # Conversation memory (Policy B) + Knowledge base RAG
            # For weather (and other ephemeral tools), DO NOT pull conversation memory or KB RAG.
            if (not is_tool_intent) and (not is_weather):
                convo_ctx, used_convo = retrieve_conversation_context_if_relevant(
                    conv_store=conv_store,
                    user_id=user_id,
                    query_text=text,
                )
                state["conversation_context"] = convo_ctx
                state["used_conversation_context"] = used_convo

                try:
                    docs = vector_store.similarity_search(text, k=int(state.get("policy", {}).get("top_k", 3)))
                except Exception as e:
                    print(f"[Delilah Brain] qdrant lookup failed: {e}", flush=True)
                    docs = []

                rag_ctx = "\n\n".join(getattr(d, "page_content", "") for d in docs) if docs else ""
            else:
                state["conversation_context"] = ""
                state["used_conversation_context"] = False

            # Tooling
            tool_block = ""
            if is_tool_intent or is_weather:
                # Choose tool deterministically
                tool_name = state.get("tool") or (policy_tool if is_tool_intent else "weather")
                state["tool"] = tool_name
                # Phase 6.1: target_expert must follow tool_name for tool intents (prevents router_hint bleed-through)
                if tool_name == "weather":
                    state["target_expert"] = "weather"
                elif isinstance(tool_name, str) and tool_name.startswith("system."):
                    state["target_expert"] = "system"
                elif isinstance(tool_name, str) and tool_name.startswith("mqtt."):
                    state["target_expert"] = "mqtt"
                else:
                    state["target_expert"] = state.get("target_expert") or "general"
                trace_id = (state.get("trace_id") or "trace_missing").strip() or "trace_missing"

                try:
                    started_at = datetime.now(timezone.utc)

                    # Build tool args + ToolRequest
                    req = None
                    if tool_name == "weather":
                        state["tool_args"] = parse_weather_args(text)
                        # Phase 6.x: weather arg parsing fallback (handles shorthand like 'weather san juan pr')
                        if not state.get("tool_args"):
                            state["tool_args"] = {}
                        if not state["tool_args"].get("location") and not state["tool_args"].get("location_name"):
                            parsed = parse_weather_args(text)
                            for k, v in (parsed or {}).items():
                                if v and not state["tool_args"].get(k):
                                    state["tool_args"][k] = v
                        if not state["tool_args"].get("location") and not state["tool_args"].get("location_name"):
                            state["tool_args"]["location"] = DEFAULT_LOCATION_QUERY
                        req = ToolRequest(
                            trace_id=trace_id,
                            tool_name="weather",
                            args=state["tool_args"],
                            purpose="Realtime weather lookup (weather.gov)",
                            risk_level="READ_ONLY",
                        )
                    elif tool_name == "system.health_check":
                        state["tool_args"] = {}
                        req = ToolRequest(
                            trace_id=trace_id,
                            tool_name="system.health_check",
                            args=state["tool_args"],
                            purpose="Local system health check",
                            risk_level="READ_ONLY",
                        )
                    elif tool_name == "system.get_versions":
                        state["tool_args"] = {}
                        req = ToolRequest(
                            trace_id=trace_id,
                            tool_name="system.get_versions",
                            args=state["tool_args"],
                            purpose="Return running component versions",
                            risk_level="READ_ONLY",
                        )
                    elif tool_name == "mqtt.publish":
                        import re as _re
                        t = (text or "").strip()

                        state["tool_args"] = {}

                        # Labeled form: topic:/payload:
                        mt = _re.search(r"(?:topic\s*:?\s*)([A-Za-z0-9_\-\/\.]+)", t, flags=_re.IGNORECASE)
                        mp = _re.search(r"(?:payload\s*:?\s*)(.+)$", t, flags=_re.IGNORECASE)
                        if mt:
                            state["tool_args"]["topic"] = mt.group(1)
                        if mp:
                            state["tool_args"]["payload"] = mp.group(1).strip()

                        # Shorthand form: mqtt publish <topic> <payload...>
                        # Example: "mqtt publish delilah/test hello"
                        if (not state["tool_args"].get("topic")) or (state["tool_args"].get("payload") is None):
                            ms = _re.match(
                                r"^\s*mqtt\s+publish\s+(?P<topic>[A-Za-z0-9_\-\/\.]+)\s+(?P<payload>.+?)\s*$",
                                t,
                                flags=_re.IGNORECASE,
                            )
                            if ms:
                                state["tool_args"].setdefault("topic", ms.group("topic"))
                                if state["tool_args"].get("payload") is None:
                                    state["tool_args"]["payload"] = (ms.group("payload") or "").strip()
                        if not state["tool_args"].get("topic") or not state["tool_args"].get("payload"):
                            state["tool_result"] = {"ok": False, "error": "mqtt.publish requires topic and payload", "result": {"tool": "mqtt.publish"}}
                            state["tool_error"] = state["tool_result"]["error"]
                            req = None
                        else:
                            req = ToolRequest(
                                trace_id=trace_id,
                                tool_name="mqtt.publish",
                                args=state["tool_args"],
                                purpose="Publish MQTT message (explicit user request)",
                                risk_level="WRITE",
                            )
                    else:
                        state["tool_args"] = {}
                        state["tool_result"] = {"ok": False, "error": f"unknown tool: {tool_name}", "result": {"tool": tool_name}}
                        state["tool_error"] = state["tool_result"]["error"]
                        req = None

                    if req is not None:
                        res = executor.execute(req)
                        ended_at = datetime.now(timezone.utc)
                        state["tool_result"] = res.to_dict()
                        state["tool_error"] = None if res.ok else res.error

                        # Never persist ephemeral tools
                        if state["tool"] not in EPHEMERAL_TOOLS:
                            log_tool_call(
                                trace_id=state.get("trace_id"),
                                user_id=user_id,
                                tool=state["tool"],
                                args=state["tool_args"],
                                result=state["tool_result"],
                                started_at=started_at,
                                ended_at=ended_at,
                            )

                except Exception as e:
                    state["tool_error"] = str(e)
                    state["tool_result"] = {"ok": False, "error": str(e), "result": {"tool": state.get("tool")}}

                # Build a context tool block for LLM use (if needed)
                if (state.get("tool_result") or {}).get("ok"):
                    _r = (state.get("tool_result") or {}).get("result") or {}
                    tool_block = f"TOOL RESULT ({state.get('tool')}): {_r.get('summary','')}"


            # Build context
            ctx_parts: List[str] = []
            if persona:
                ctx_parts.append("PERSONA:\n" + persona)
            if used_convo and convo_ctx:
                ctx_parts.append("CONVERSATION MEMORY:\n" + convo_ctx)
            if rag_ctx:
                ctx_parts.append("KNOWLEDGE BASE:\n" + rag_ctx)
            if tool_block:
                ctx_parts.append(tool_block)

            context = "\n\n".join(ctx_parts).strip()
            state["context"] = context
            state["used_context"] = bool(context)
            state["num_docs"] = len(docs)

            # Phase 6 tool-first invariant: if a tool succeeded, return a deterministic tool answer (no LLM)
            if state.get("tool") and (state.get("tool_result") or {}).get("ok"):
                tool = state.get("tool")
                tr = state.get("tool_result") or {}
                rr = tr.get("result") or {}
                summ = (rr.get("summary") or "").strip()
                if tool == "weather":
                    loc = rr.get("location") or (state.get("tool_args") or {}).get("location") or ""
                    state["answer"] = f"{loc}: {summ}" if loc else summ
                else:
                    state["answer"] = summ or str(rr)
                state["source"] = "tool"
                state["used_context"] = False
                state["num_docs"] = 0
                state["used_conversation_context"] = False
                return state

            # Tool intent hard-stop: if a tool failed, DO NOT fall back to LLM (prevents hallucinations).
            if state.get("tool") and (state.get("tool_result") or {}).get("ok") is False:
                tool = state.get("tool")
                tr = state.get("tool_result") or {}
                rr = tr.get("result") or {}
                err = tr.get("error") or rr.get("error") or state.get("tool_error") or "tool failed"
                if tool == "weather":
                    loc = rr.get("location") or (state.get("tool_args") or {}).get("location") or (state.get("tool_args") or {}).get("location_name") or ""
                    state["answer"] = f"Weather lookup failed for {loc}: {err}" if loc else f"Weather lookup failed: {err}"
                else:
                    state["answer"] = f"{tool} failed: {err}"
                state["source"] = "tool_error"
                state["used_context"] = False
                state["num_docs"] = 0
                state["used_conversation_context"] = False
                return state


            # Prompt
            if context:
                prompt = f"SYSTEM:\nUse the provided context when relevant.\n\nCONTEXT:\n{context}\n\nUSER:\n{text}\n\nASSISTANT:"
            else:
                prompt = f"USER:\n{text}\n\nASSISTANT:"

            try:
                state["answer"] = (llm.invoke(prompt) or "").strip()
            except Exception as e:
                print(f"[Delilah Brain] llm invoke failed: {e}", flush=True)
                state["answer"] = "I ran into an internal dependency error. Please try again."
            return state

    return _Graph()
