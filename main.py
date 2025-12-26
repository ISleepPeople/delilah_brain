# -*- coding: utf-8 -*-
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List, Any, Dict
import os
import json
import time
import uuid

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

# LangChain (keep your current Ollama usage)
from langchain_community.llms import Ollama
from langchain_community.embeddings import OllamaEmbeddings

from orchestrator import build_simple_graph, BrainState

try:
    import psycopg
except Exception:
    psycopg = None


# ============================
# STRUCTURED LOGGING
# ============================

def jlog(event: str, **fields):
    payload = {"event": event, **fields}
    try:
        print(json.dumps(payload, ensure_ascii=False), flush=True)
    except Exception:
        print(str(payload), flush=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ============================
# CONFIG (pinned + validated)
# ============================

REQUIRED_ENV = [
    "OLLAMA_URL",
    "QDRANT_URL",
    "DATABASE_URL",
    "CHAT_MODEL",
    "EMBED_MODEL",
    "EMBED_DIM",
    "COL_KNOWLEDGE",
    "COL_ROUTER_HINTS",
    "COL_PERSONA",
    "COL_CONVO",
]

def validate_config():
    missing = [k for k in REQUIRED_ENV if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {missing}")
    try:
        int(os.getenv("EMBED_DIM", "0"))
    except Exception:
        raise RuntimeError("EMBED_DIM must be an integer")


def redact_database_url(db: str) -> str:
    if not db:
        return ""
    redacted = db
    if "://" in db and "@" in db:
        try:
            prefix, rest = db.split("://", 1)
            creds, host = rest.split("@", 1)
            if ":" in creds:
                user, _pw = creds.split(":", 1)
                redacted = f"{prefix}://{user}:***@{host}"
        except Exception:
            redacted = "***"
    return redacted


def log_config_startup():
    jlog(
        "config_startup",
        ollama_url=os.getenv("OLLAMA_URL"),
        qdrant_url=os.getenv("QDRANT_URL"),
        database_url=redact_database_url(os.getenv("DATABASE_URL", "")),
        chat_model=os.getenv("CHAT_MODEL"),
        embed_model=os.getenv("EMBED_MODEL"),
        embed_dim=int(os.getenv("EMBED_DIM", "0")),
        col_knowledge=os.getenv("COL_KNOWLEDGE"),
        col_router_hints=os.getenv("COL_ROUTER_HINTS"),
        col_persona=os.getenv("COL_PERSONA"),
        col_convo=os.getenv("COL_CONVO"),
        pg_logging_enabled=os.getenv("PG_LOGGING_ENABLED", "0"),
        debug=os.getenv("DELILAH_DEBUG", "0"),
    )


QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_TIMEOUT_S = int(os.getenv("QDRANT_TIMEOUT_S", "5"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

CHAT_MODEL = os.getenv("CHAT_MODEL", "llama3:8b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))

COL_KNOWLEDGE = os.getenv("COL_KNOWLEDGE", "delilah_knowledge")
COL_ROUTER_HINTS = os.getenv("COL_ROUTER_HINTS", "router_hints")
COL_PERSONA = os.getenv("COL_PERSONA", "persona_memory")
COL_CONVO = os.getenv("COL_CONVO", "conversation_memory")

DATABASE_URL = os.getenv("DATABASE_URL")
PG_LOGGING_ENABLED = os.getenv("PG_LOGGING_ENABLED", "0") == "1"
# Tools whose outputs/turns are ephemeral and should NEVER be persisted in Postgres
# (and should also not be stored in conversation_memory)
EPHEMERAL_TOOLS = {"weather", "sports", "stocks"}



def new_trace_id() -> str:
    return str(uuid.uuid4())


def pg_log_turn(**kw):
    # Non-blocking; never crashes runtime
    if not PG_LOGGING_ENABLED or not DATABASE_URL or psycopg is None:
        return
    try:
        with psycopg.connect(DATABASE_URL, autocommit=True) as c:
            c.execute(
                """
                INSERT INTO brain.turns
                (turn_id, trace_id, user_id, role, text, used_context, used_conversation_context,
                 num_docs, target_expert, tool, latency_ms, meta)
                VALUES
                (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    str(uuid.uuid4()),
                    kw.get("trace_id"),
                    kw.get("user_id"),
                    kw.get("role"),
                    kw.get("text"),
                    kw.get("used_context"),
                    kw.get("used_conversation_context"),
                    kw.get("num_docs"),
                    kw.get("target_expert"),
                    kw.get("tool"),
                    kw.get("latency_ms"),
                    json.dumps(kw.get("meta") or {}),
                ),
            )
    except Exception as e:
        print(f"[PG_LOGGER] turn log failed: {e}", flush=True)


def qdrant_collection_exists(name: str) -> bool:
    """
    Existence check via REST list endpoint (stable across versions).
    """
    try:
        r = requests.get(f"{QDRANT_URL}/collections", timeout=2)
        r.raise_for_status()
        cols = r.json().get("result", {}).get("collections", [])
        names = [c.get("name") for c in cols if isinstance(c, dict)]
        return name in names
    except Exception as e:
        print(f"[Delilah Brain] qdrant_collection_exists check failed: {e}", flush=True)
        return False


# ============================
# Minimal deterministic Qdrant store adapter
# ============================

class Doc:
    def __init__(self, page_content: str, metadata: Optional[dict] = None):
        self.page_content = page_content
        self.metadata = metadata or {}


class SimpleQdrantStore:
    """
    A tiny adapter that provides the exact surface area your orchestrator and routes use:
      - add_texts(texts, metadatas)
      - similarity_search(query, k)
      - similarity_search_with_score(query, k)

    It uses ONLY QdrantClient.query_points(), which your environment supports.
    It also preserves your existing payload schema:
      payload = {"page_content": <text>, "metadata": <dict>}
    """
    def __init__(self, *, client: QdrantClient, embeddings: OllamaEmbeddings, collection_name: str):
        self.client = client
        self.embeddings = embeddings
        self.collection_name = collection_name

    def add_texts(self, texts: List[str], metadatas: Optional[List[dict]] = None) -> List[str]:
        metadatas = metadatas or [{} for _ in texts]
        vectors = self.embeddings.embed_documents(texts)
        ids: List[str] = []
        points: List[PointStruct] = []
        for text, meta, vec in zip(texts, metadatas, vectors):
            pid = str(uuid.uuid4())
            ids.append(pid)
            payload = {
                "page_content": text,
                "metadata": meta or {},
            }
            points.append(PointStruct(id=pid, vector=vec, payload=payload))
        self.client.upsert(collection_name=self.collection_name, points=points)
        return ids

    def similarity_search(self, query: str, k: int = 4) -> List[Doc]:
        rows = self.similarity_search_with_score(query, k=k)
        return [d for d, _s in rows]

    def similarity_search_with_score(self, query: str, k: int = 4) -> List[tuple[Doc, float]]:
        qvec = self.embeddings.embed_query(query)
        res = self.client.query_points(
            collection_name=self.collection_name,
            query=qvec,
            limit=k,
            with_payload=True,
            with_vectors=False,
        )
        points = getattr(res, "points", res)
        out: List[tuple[Doc, float]] = []
        for p in points:
            payload = getattr(p, "payload", None) or {}
            text = payload.get("page_content") or payload.get("text") or ""
            meta = payload.get("metadata") or {}
            score = float(getattr(p, "score", 0.0) or 0.0)
            out.append((Doc(text, meta), score))
        return out


def build_app_state():
    """
    Deterministic one-time init.
    Mode B: attach to existing collections; fail fast if missing.
    """
    qdrant_client = QdrantClient(url=QDRANT_URL, timeout=QDRANT_TIMEOUT_S)
    llm = Ollama(base_url=OLLAMA_URL, model=CHAT_MODEL)
    embeddings = OllamaEmbeddings(base_url=OLLAMA_URL, model=EMBED_MODEL)

    required = [COL_KNOWLEDGE, COL_ROUTER_HINTS, COL_PERSONA, COL_CONVO]
    missing = [c for c in required if not qdrant_collection_exists(c)]
    if missing:
        raise RuntimeError(
            f"Missing Qdrant collections: {missing}. "
            f"Mode B requires bootstrapping collections once (admin step) before running the API."
        )

    vector_store = SimpleQdrantStore(client=qdrant_client, embeddings=embeddings, collection_name=COL_KNOWLEDGE)
    router_store = SimpleQdrantStore(client=qdrant_client, embeddings=embeddings, collection_name=COL_ROUTER_HINTS)
    persona_store = SimpleQdrantStore(client=qdrant_client, embeddings=embeddings, collection_name=COL_PERSONA)
    conv_store = SimpleQdrantStore(client=qdrant_client, embeddings=embeddings, collection_name=COL_CONVO)

    graph = build_simple_graph(
        llm=llm,
        vector_store=vector_store,
        conv_store=conv_store,
        persona_store=persona_store,
        router_store=router_store,
    )

    return {
        "qdrant_client": qdrant_client,
        "llm": llm,
        "embeddings": embeddings,
        "vector_store": vector_store,
        "router_store": router_store,
        "persona_store": persona_store,
        "conv_store": conv_store,
        "graph": graph,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_config()
    log_config_startup()

    t0 = time.perf_counter()
    try:
        app.state.brain = build_app_state()
        jlog("startup_ready", init_ms=int((time.perf_counter() - t0) * 1000))
    except Exception as e:
        jlog("startup_failed", error=str(e))
        raise
    yield
    jlog("shutdown", at=utc_now_iso())


app = FastAPI(title="Delilah Brain v2", version="2.0.0", lifespan=lifespan)


# ============================
# MODELS
# ============================

class IngestRequest(BaseModel):
    text: str
    user_id: str = "ryan"
    source: Optional[str] = None
    tags: Optional[List[str]] = None

class RouterHintRequest(BaseModel):
    text: str
    user_id: str = "ryan"
    target_expert: str
    notes: Optional[str] = None

class PersonaRequest(BaseModel):
    text: str
    user_id: str = "ryan"
    mood: Optional[str] = None
    style: Optional[str] = None
    tags: Optional[List[str]] = None
    source: Optional[str] = None

class AskRequest(BaseModel):
    text: str
    user_id: str = "ryan"


# ============================
# ROUTES
# ============================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "chat_model": CHAT_MODEL,
        "embed_model": EMBED_MODEL,
        "collections": {
            "knowledge": COL_KNOWLEDGE,
            "router_hints": COL_ROUTER_HINTS,
            "persona": COL_PERSONA,
            "conversation": COL_CONVO,
        },
    }


@app.get("/health/deps")
def health_deps():
    deps: Dict[str, Any] = {}

    try:
        r = requests.get(f"{QDRANT_URL}/collections", timeout=2)
        deps["qdrant"] = {"ok": r.ok, "status_code": r.status_code}
    except Exception as e:
        deps["qdrant"] = {"ok": False, "error": str(e)}

    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        deps["ollama"] = {"ok": r.ok, "status_code": r.status_code}
    except Exception as e:
        deps["ollama"] = {"ok": False, "error": str(e)}

    try:
        if not DATABASE_URL:
            deps["postgres"] = {"ok": False, "error": "DATABASE_URL not set"}
        elif psycopg is None:
            deps["postgres"] = {"ok": False, "error": "psycopg not installed"}
        else:
            with psycopg.connect(DATABASE_URL, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
            deps["postgres"] = {"ok": True}
    except Exception as e:
        deps["postgres"] = {"ok": False, "error": str(e)}

    overall_ok = all(d.get("ok") for d in deps.values())
    return {"ok": overall_ok, "deps": deps}


def store_turn(*, user_id: str, role: str, text: str):
    try:
        conv_store = app.state.brain["conv_store"]
        conv_store.add_texts(
            [f"role:{role}\nuser_id:{user_id}\ntimestamp:{utc_now_iso()}\n\n{text}"],
            metadatas=[{"user_id": user_id, "role": role, "timestamp": utc_now_iso()}],
        )
    except Exception as e:
        print(f"[Delilah Brain] conversation_memory store warning: {e}", flush=True)


@app.post("/ingest")
def ingest(req: IngestRequest):
    try:
        vs = app.state.brain["vector_store"]
        meta = {
            "user_id": req.user_id,
            "source": req.source,
            "ts": time.time(),
        }
        vs.add_texts([req.text], metadatas=[meta])
        return {
            "status": "ok",
            "inserted": 1,
            "collection": COL_KNOWLEDGE,
            "trace_id": new_trace_id(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")


@app.post("/router_hint")
def router_hint(req: RouterHintRequest):
    try:
        rs = app.state.brain["router_store"]
        meta = {
            "user_id": req.user_id,
            "target_expert": req.target_expert,
            "notes": req.notes or "",
            "timestamp": utc_now_iso(),
        }
        rs.add_texts([req.text], metadatas=[meta])
        return {
            "status": "ok",
            "inserted": 1,
            "collection": COL_ROUTER_HINTS,
            "trace_id": new_trace_id(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Router hint failed: {e}")


@app.post("/persona_memory")
def persona_memory(req: PersonaRequest):
    try:
        ps = app.state.brain["persona_store"]
        meta = {
            "user_id": req.user_id,
            "mood": req.mood or "",
            "style": req.style or "",
            "tags": req.tags or [],
            "source": req.source or "manual",
            "timestamp": utc_now_iso(),
        }
        ps.add_texts([req.text], metadatas=[meta])
        return {
            "status": "ok",
            "inserted": 1,
            "collection": COL_PERSONA,
            "trace_id": new_trace_id(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Persona memory failed: {e}")


@app.post("/ask")
def ask(req: AskRequest):
    try:
        user_id = (req.user_id or "ryan").strip() or "ryan"
        text = (req.text or "").strip()
        trace_id = new_trace_id()

        t0 = time.perf_counter()
        jlog("ask_start", trace_id=trace_id, user_id=user_id)

        graph = app.state.brain["graph"]
        initial_state: BrainState = {"text": text, "user_id": user_id, "trace_id": trace_id}
        result = graph.invoke(initial_state)

        tool = (result.get("tool") or "").strip().lower() or None
        is_ephemeral = tool in EPHEMERAL_TOOLS if tool else False

        # Only persist turns if this was NOT an ephemeral-tool request (e.g., weather).
        if not is_ephemeral:
            pg_log_turn(trace_id=trace_id, user_id=user_id, role="user", text=text, meta={"endpoint": "/ask"})
            store_turn(user_id=user_id, role="user", text=text)

        answer = (result.get("answer") or "").strip() or "I ran into an internal issue and couldn't generate a response."

        if not is_ephemeral:
            store_turn(user_id=user_id, role="assistant", text=answer)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        jlog(
            "ask_done",
            trace_id=trace_id,
            user_id=user_id,
            latency_ms=latency_ms,
            used_context=bool(result.get("used_context")),
            used_conversation_context=bool(result.get("used_conversation_context")),
            num_docs=int(result.get("num_docs") or 0),
            target_expert=(result.get("target_expert") or "general"),
            tool=result.get("tool"),
        )

        if not is_ephemeral:
            pg_log_turn(
                trace_id=trace_id,
                user_id=user_id,
                role="assistant",
                text=answer,
                used_context=bool(result.get("used_context")),
                used_conversation_context=bool(result.get("used_conversation_context")),
                num_docs=int(result.get("num_docs") or 0),
                target_expert=(result.get("target_expert") or "general"),
                tool=result.get("tool"),
                latency_ms=latency_ms,
                meta={"source": "rag_llm_graph"},
            )

        return {
            "trace_id": trace_id,
            "text": answer,
            "source": "rag_llm_graph",
            "used_context": bool(result.get("used_context")),
            "num_docs": int(result.get("num_docs") or 0),
            "used_conversation_context": bool(result.get("used_conversation_context")),
            "target_expert": result.get("target_expert") or "general",
            "tool": result.get("tool"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Brain error: {e}")
