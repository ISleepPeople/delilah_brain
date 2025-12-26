from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import os

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from langchain_community.llms import Ollama
from langchain_community.embeddings import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore

from orchestrator import build_simple_graph, BrainState

import time, uuid, json
try:
    import psycopg
except Exception:
    psycopg=None

DATABASE_URL=os.getenv('DATABASE_URL')
PG_LOGGING_ENABLED=os.getenv('PG_LOGGING_ENABLED','0')=='1'

def new_trace_id():
    return str(uuid.uuid4())

def pg_log_turn(**kw):
    if not PG_LOGGING_ENABLED or not DATABASE_URL or psycopg is None: return
    try:
        with psycopg.connect(DATABASE_URL, autocommit=True) as c:
            c.execute("INSERT INTO brain.turns (turn_id,trace_id,user_id,role,text,used_context,used_conversation_context,num_docs,target_expert,tool,latency_ms,meta) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (str(uuid.uuid4()), kw.get('trace_id'), kw.get('user_id'), kw.get('role'), kw.get('text'), kw.get('used_context'), kw.get('used_conversation_context'), kw.get('num_docs'), kw.get('target_expert'), kw.get('tool'), kw.get('latency_ms'), json.dumps(kw.get('meta') or {})))
    except Exception as e:
        print(f'[PG_LOGGER] turn log failed: {e}', flush=True)

# ============================
# CONFIG
# ============================

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")

# Defaults are safe; override via env when you decide.
CHAT_MODEL = os.getenv("CHAT_MODEL", "llama3:8b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))

COL_KNOWLEDGE = os.getenv("COL_KNOWLEDGE", "delilah_knowledge")
COL_ROUTER = os.getenv("COL_ROUTER_HINTS", "router_hints")
COL_PERSONA = os.getenv("COL_PERSONA", "persona_memory")
COL_CONVO = os.getenv("COL_CONVO", "conversation_memory")

os.environ.setdefault("DELILAH_UA", "delilah-server (ryan.j.werner80@gmail.com)")

# ============================
# APP
# ============================

app = FastAPI(title="Delilah Brain v2", version="2.0.0")

# ============================
# HELPERS
# ============================

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def ensure_collection(qdrant: QdrantClient, name: str):
    try:
        qdrant.get_collection(name)
        return
    except Exception:
        pass

    qdrant.create_collection(
        collection_name=name,
        vectors_config=qmodels.VectorParams(size=EMBED_DIM, distance=qmodels.Distance.COSINE),
    )

# ============================
# LAZY SINGLETONS (avoid import-time hangs)
# ============================

_qdrant = None
_llm = None
_embeddings = None
_vector_store = None
_router_store = None
_persona_store = None
_conv_store = None
_graph = None

def get_graph():
    global _qdrant, _llm, _embeddings, _vector_store, _router_store, _persona_store, _conv_store, _graph
    if _graph is not None:
        return _graph

    _qdrant = QdrantClient(url=QDRANT_URL)
    _llm = Ollama(base_url=OLLAMA_URL, model=CHAT_MODEL)
    _embeddings = OllamaEmbeddings(base_url=OLLAMA_URL, model=EMBED_MODEL)

    for c in [COL_KNOWLEDGE, COL_ROUTER, COL_PERSONA, COL_CONVO]:
        ensure_collection(_qdrant, c)

    _vector_store = QdrantVectorStore(client=_qdrant, collection_name=COL_KNOWLEDGE, embedding=_embeddings)
    _router_store = QdrantVectorStore(client=_qdrant, collection_name=COL_ROUTER, embedding=_embeddings)
    _persona_store = QdrantVectorStore(client=_qdrant, collection_name=COL_PERSONA, embedding=_embeddings)
    _conv_store = QdrantVectorStore(client=_qdrant, collection_name=COL_CONVO, embedding=_embeddings)

    _graph = build_simple_graph(
        llm=_llm,
        vector_store=_vector_store,
        conv_store=_conv_store,
        persona_store=_persona_store,
        router_store=_router_store,
    )
    return _graph

def store_turn(*, user_id: str, role: str, text: str):
    try:
        g = get_graph()
        # conv_store is created in get_graph; grab from module globals
        global _conv_store
        payload = {
            "page_content": f"role:{role}\nuser_id:{user_id}\ntimestamp:{utc_now_iso()}\n\n{text}",
            "metadata": {"user_id": user_id, "role": role, "timestamp": utc_now_iso()},
        }
        _conv_store.add_texts([payload["page_content"]], metadatas=[payload["metadata"]])
    except Exception as e:
        print(f"[Delilah Brain] conversation_memory store warning: {e}", flush=True)

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
    # Do not force graph init here; report config + allow fast check.
    return {
        "status": "ok",
        "chat_model": CHAT_MODEL,
        "embed_model": EMBED_MODEL,
        "collections": {
            "knowledge": COL_KNOWLEDGE,
            "router_hints": COL_ROUTER,
            "persona": COL_PERSONA,
            "conversation": COL_CONVO,
        },
    }

@app.post("/ingest")
def ingest(req: IngestRequest):
    try:
        get_graph()
        global _vector_store
        meta = {
            "user_id": req.user_id,
            "source": req.source or "manual",
            "tags": req.tags or [],
            "timestamp": utc_now_iso(),
        }
        _vector_store.add_texts([req.text], metadatas=[meta])
        return {"status": "ok", "inserted": 1, "collection": COL_KNOWLEDGE}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")

@app.post("/router_hint")
def router_hint(req: RouterHintRequest):
    try:
        get_graph()
        global _router_store
        meta = {
            "user_id": req.user_id,
            "target_expert": req.target_expert,
            "notes": req.notes or "",
            "timestamp": utc_now_iso(),
        }
        _router_store.add_texts([req.text], metadatas=[meta])
        return {"status": "ok", "inserted": 1, "collection": COL_ROUTER}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Router hint failed: {e}")

@app.post("/persona_memory")
def persona_memory(req: PersonaRequest):
    try:
        get_graph()
        global _persona_store
        meta = {
            "user_id": req.user_id,
            "mood": req.mood or "",
            "style": req.style or "",
            "tags": req.tags or [],
            "source": req.source or "manual",
            "timestamp": utc_now_iso(),
        }
        _persona_store.add_texts([req.text], metadatas=[meta])
        return {"status": "ok", "inserted": 1, "collection": COL_PERSONA}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Persona memory failed: {e}")

@app.post("/ask")
def ask(req: AskRequest):
    try:
        user_id = (req.user_id or "ryan").strip() or "ryan"
        text = (req.text or "").strip()
        trace_id = new_trace_id()
        t0 = time.perf_counter()
        pg_log_turn(trace_id=trace_id,user_id=user_id,role="user",text=text,meta={"endpoint":"/ask"})
        store_turn(user_id=user_id, role="user", text=text)

        graph = get_graph()
        initial_state: BrainState = {"text": text, "user_id": user_id, "trace_id": trace_id}
        result = graph.invoke(initial_state)

        answer = (result.get("answer") or "").strip() or "I ran into an internal issue and couldn't generate a response."
        store_turn(user_id=user_id, role="assistant", text=answer)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        pg_log_turn(trace_id=trace_id,user_id=user_id,role="assistant",text=answer,used_context=bool(result.get("used_context")),used_conversation_context=bool(result.get("used_conversation_context")),num_docs=int(result.get("num_docs") or 0),target_expert=(result.get("target_expert") or "general"),tool=result.get("tool"),latency_ms=latency_ms,meta={"source":"rag_llm_graph"})

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
