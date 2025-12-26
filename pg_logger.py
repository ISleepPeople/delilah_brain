import os
import uuid
import json
import psycopg
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL")
PG_LOGGING_ENABLED = os.getenv("PG_LOGGING_ENABLED", "0") == "1"

def _utcnow():
    return datetime.now(timezone.utc)

def new_trace_id() -> str:
    return str(uuid.uuid4())

def _get_conn():
    if not DATABASE_URL:
        return None
    return psycopg.connect(DATABASE_URL, autocommit=True)

def log_turn(
    *,
    trace_id: str,
    user_id: str,
    role: str,
    text: str,
    used_context: bool = None,
    used_conversation_context: bool = None,
    num_docs: int = None,
    target_expert: str = None,
    tool: str = None,
    latency_ms: int = None,
    meta: dict = None,
):
    if not PG_LOGGING_ENABLED:
        return
    try:
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO brain.turns (
                  turn_id, trace_id, user_id, role, text,
                  used_context, used_conversation_context, num_docs,
                  target_expert, tool, latency_ms, meta
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    str(uuid.uuid4()),
                    trace_id,
                    user_id,
                    role,
                    text,
                    used_context,
                    used_conversation_context,
                    num_docs,
                    target_expert,
                    tool,
                    latency_ms,
                    json.dumps(meta or {}),
                ),
            )
    except Exception as e:
        # Never block the assistant
        print(f"[PG_LOGGER] turn log failed: {e}", flush=True)

def log_tool_call(
    *,
    trace_id: str,
    user_id: str,
    tool: str,
    args: dict,
    result: dict = None,
    error: str = None,
    started_at,
    ended_at,
):
    if not PG_LOGGING_ENABLED:
        return
    try:
        latency_ms = int((ended_at - started_at).total_seconds() * 1000)
        with _get_conn() as conn:
            conn.execute(
                """
                INSERT INTO brain.tool_calls (
                  tool_call_id, trace_id, user_id, tool,
                  args, result, error,
                  started_at, ended_at, latency_ms
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    str(uuid.uuid4()),
                    trace_id,
                    user_id,
                    tool,
                    json.dumps(args or {}),
                    json.dumps(result) if result is not None else None,
                    error,
                    started_at,
                    ended_at,
                    latency_ms,
                ),
            )
    except Exception as e:
        print(f"[PG_LOGGER] tool log failed: {e}", flush=True)
