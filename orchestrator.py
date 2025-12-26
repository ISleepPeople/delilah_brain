# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict, List, Tuple
from datetime import datetime, timezone
import os
import re

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

    location_query = (
        tool_args.get("location")
        or tool_args.get("location_name")
        or DEFAULT_LOCATION_QUERY
    )

    headers = {
        "User-Agent": "Delilah/1.0 (contact: local)",
        "Accept": "application/geo+json",
    }

    try:
        # 1) Resolve location to lat/lon
        geo_resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location_query, "format": "json", "limit": 1},
            headers=headers,
            timeout=5,
        )
        geo_resp.raise_for_status()
        geo = geo_resp.json()

        if not geo:
            return {
                "ok": False,
                "error": f"Could not resolve location '{location_query}'",
                "source": "weather.gov",
            }

        lat = geo[0]["lat"]
        lon = geo[0]["lon"]

        # 2) Get weather.gov grid endpoint
        points_resp = requests.get(
            f"https://api.weather.gov/points/{lat},{lon}",
            headers=headers,
            timeout=5,
        )
        points_resp.raise_for_status()
        points = points_resp.json()

        forecast_url = points["properties"]["forecast"]

        # 3) Get forecast
        forecast_resp = requests.get(
            forecast_url,
            headers=headers,
            timeout=5,
        )
        forecast_resp.raise_for_status()
        forecast = forecast_resp.json()

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
    m = re.search(r"\bweather in (.+)$", (query_text or "").lower())
    return {"location_name": m.group(1)} if m else {}


# ============================
# GRAPH
# ============================

def build_simple_graph(*, llm, vector_store, conv_store, persona_store, router_store):
    class _Graph:
        def invoke(self, state: BrainState) -> BrainState:
            text = (state.get("text") or "").strip()
            user_id = (state.get("user_id") or "ryan").strip() or "ryan"

            state.update({
                "tool": None,
                "tool_args": {},
                "tool_result": None,
                "tool_error": None,
            })

            # Router hints
            state["target_expert"] = router_hint_target(
                router_store=router_store,
                user_id=user_id,
                query_text=text,
            )

            # Persona
            persona = persona_directives(persona_store=persona_store, user_id=user_id)

            # Determine if this is an ephemeral tool intent (weather, etc.)
            is_weather = detect_weather_intent(text)

            # Always initialize locals so later code cannot reference undefined names
            convo_ctx = ""
            used_convo = False
            docs: List[Any] = []
            rag_ctx = ""

            # Conversation memory (Policy B) + Knowledge base RAG
            # For weather (and other ephemeral tools), DO NOT pull conversation memory or KB RAG.
            if not is_weather:
                convo_ctx, used_convo = retrieve_conversation_context_if_relevant(
                    conv_store=conv_store,
                    user_id=user_id,
                    query_text=text,
                )
                state["conversation_context"] = convo_ctx
                state["used_conversation_context"] = used_convo

                try:
                    docs = vector_store.similarity_search(text, k=3)
                except Exception as e:
                    print(f"[Delilah Brain] qdrant lookup failed: {e}", flush=True)
                    docs = []

                rag_ctx = "\n\n".join(getattr(d, "page_content", "") for d in docs) if docs else ""
            else:
                state["conversation_context"] = ""
                state["used_conversation_context"] = False

            # Tooling
            tool_block = ""
            if is_weather:
                state["tool"] = "weather"
                state["tool_args"] = parse_weather_args(text)

                try:
                    started_at = datetime.now(timezone.utc)
                    state["tool_result"] = weather_tool(state["tool_args"])
                    ended_at = datetime.now(timezone.utc)

                    # Never persist ephemeral tool calls
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
                    state["tool_result"] = {"ok": False, "error": str(e)}

                if (state.get("tool_result") or {}).get("ok"):
                    tool_block = f"TOOL RESULT (Weather): {state['tool_result'].get('summary','')}"

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
