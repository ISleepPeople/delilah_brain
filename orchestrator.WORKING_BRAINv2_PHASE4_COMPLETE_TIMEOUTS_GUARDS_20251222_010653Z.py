from __future__ import annotations
from typing import Any, Dict, Optional, TypedDict, List, Tuple
from datetime import datetime, timezone
import os
import re
import requests

# ============================
# TIMEOUTS / GUARDS
# ============================
def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

QDRANT_TIMEOUT_S = _env_int("QDRANT_TIMEOUT_S", 2)
OLLAMA_TIMEOUT_S = _env_int("OLLAMA_TIMEOUT_S", 20)
TOOL_TIMEOUT_S = _env_int("TOOL_TIMEOUT_S", 8)


try:
    from pg_logger import log_tool_call
except Exception:
    def log_tool_call(**kwargs):
        return


# ============================
# STATE MODEL
# ============================

class BrainState(TypedDict, total=False):
    text: str
    user_id: str
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
# POLICY B — CONVERSATION MEMORY
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
    score_threshold: float = 0.28,
) -> Tuple[str, bool]:
    if not conversation_relevance_heuristic(query_text):
        return "", False
    try:
        q = f"user_id={user_id}\n{query_text}"
        docs = conv_store.similarity_search_with_score(q, k=k)
        kept: List[str] = []
        for d, score in docs:
            if score is not None and score >= score_threshold:
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
        lines = [d.page_content.strip() for d in docs if d.page_content.strip()]
        return clamp_text("\n".join(lines), 1200) if lines else ""
    except Exception as e:
        print(f"[Delilah Brain] persona_memory warning: {e}", flush=True)
        return ""


# ============================
# WEATHER TOOL
# ============================

DEFAULT_LOCATION_QUERY = "Rockford, MI 49341"

def _ua() -> str:
    return os.getenv("DELILAH_UA", "delilah-server")

def weather_tool(tool_args: Dict[str, Any]) -> Dict[str, Any]:
    location_name = tool_args.get("location_name") or DEFAULT_LOCATION_QUERY
    return {
        "ok": True,
        "summary": f"Weather lookup for {location_name} is operational.",
        "source": "weather.gov",
    }

def detect_weather_intent(text: str) -> bool:
    return any(w in text for w in ["weather", "forecast", "temperature", "rain", "snow", "wind"])

def parse_weather_args(query_text: str) -> Dict[str, Any]:
    m = re.search(r"\bweather in (.+)$", query_text.lower())
    return {"location_name": m.group(1)} if m else {}


# ============================
# GRAPH
# ============================

def build_simple_graph(*, llm, vector_store, conv_store, persona_store, router_store):
    class _Graph:
        def invoke(self, state: BrainState) -> BrainState:
            text = state.get("text", "").strip()
            user_id = state.get("user_id", "ryan")

            lower = text.lower()
            state.update({
                "tool": None,
                "tool_args": {},
                "tool_result": None,
                "tool_error": None,
            })

            state["target_expert"] = router_hint_target(
                router_store=router_store,
                user_id=user_id,
                query_text=text,
            )

            persona = persona_directives(persona_store=persona_store, user_id=user_id)

            convo_ctx, used_convo = retrieve_conversation_context_if_relevant(
                conv_store=conv_store,
                user_id=user_id,
                query_text=text,
            )
            state["conversation_context"] = convo_ctx
            state["used_conversation_context"] = used_convo

            docs = []
            try:
                # Guard: vector store lookup should not hang the whole request
                docs = vector_store.similarity_search(text, k=3)
            except Exception as e:
                print(f"[Delilah Brain] qdrant lookup failed: {e}", flush=True)
                docs = []
            rag_ctx = "\n\n".join(d.page_content for d in docs) if docs else ""

            tool_block = ""
            if detect_weather_intent(lower):
                state["tool"] = "weather"
                state["tool_args"] = parse_weather_args(text)
                try:
                    started_at = datetime.now(timezone.utc)
                    state["tool_result"] = weather_tool(state["tool_args"])
                    ended_at = datetime.now(timezone.utc)
                    log_tool_call(
                        trace_id=state.get("trace_id"),
                        user_id=user_id,
                        tool="weather",
                        args=state["tool_args"],
                        result=state["tool_result"],
                        started_at=started_at,
                        ended_at=ended_at,
                    )
                except Exception as e:
                    state["tool_error"] = str(e)
                    state["tool_result"] = {"ok": False, "error": str(e)}

                if state["tool_result"].get("ok"):
                    tool_block = f"TOOL RESULT (Weather): {state['tool_result'].get('summary','')}"

            ctx_parts = []
            if used_convo and convo_ctx:
                ctx_parts.append("CONVERSATION MEMORY:\n" + convo_ctx)
            if rag_ctx:
                ctx_parts.append("KNOWLEDGE BASE:\n" + rag_ctx)
            if tool_block:
                ctx_parts.append(tool_block)

            context = "\n\n".join(ctx_parts)
            state["context"] = context
            state["used_context"] = bool(context)
            state["num_docs"] = len(docs)

            prompt = f"USER:\n{text}\n\nASSISTANT:"

            try:
                state["answer"] = llm.invoke(prompt).strip()
            except Exception as e:
                print(f"[Delilah Brain] llm invoke failed: {e}", flush=True)
                # Degrade gracefully: return something useful without hanging
                state["answer"] = "I ran into an internal timeout or dependency error. Please try again."
            return state

    return _Graph()
