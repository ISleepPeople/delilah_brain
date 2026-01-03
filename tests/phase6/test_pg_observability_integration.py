import json
import os
import time
import urllib.error
import urllib.request

import pytest


def _http_post_json(url: str, payload: dict, timeout_s: int = 15) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from e


def _maybe_pg_connect(dsn: str):
    """
    Returns a DB connection or skips the test if no PG driver is installed.
    We skip (not fail) because this is an opt-in integration regression.
    """
    try:
        import psycopg2  # type: ignore
        return psycopg2.connect(dsn)
    except ImportError:
        pass

    try:
        import psycopg  # type: ignore
        return psycopg.connect(dsn)
    except ImportError:
        pytest.skip("No psycopg2/psycopg installed; skipping PG integration regression.")


@pytest.mark.phase6
def test_tool_call_writes_pg_turns_and_tool_calls_rows():
    """
    Integration regression (skip-safe).
    Proves: one /ask tool call results in rows in brain.turns and brain.tool_calls
    for the returned trace_id.

    This test is opt-in:
      - P6_INTEGRATION=1
      - BRAIN_URL set (e.g. http://127.0.0.1:8800)
      - DATABASE_URL set (your Postgres DSN)
    """

    if os.getenv("P6_INTEGRATION", "") != "1":
        pytest.skip("P6 integration tests disabled (set P6_INTEGRATION=1 to enable).")

    brain_url = os.getenv("BRAIN_URL")
    dsn = os.getenv("DATABASE_URL")

    if not brain_url:
        pytest.skip("BRAIN_URL not set (required for integration test).")
    if not dsn:
        pytest.skip("DATABASE_URL not set (required for integration test).")

    ask_url = brain_url.rstrip("/") + "/ask"

    # Trigger a tool call that does NOT mutate external state (mqtt tool enforces DRY_RUN unless enabled).
    resp = _http_post_json(
        ask_url,
        {"user_id": "phase6_test", "text": "mqtt publish delilah/test hello_from_pg_test"},
        timeout_s=20,
    )

    trace_id = resp.get("trace_id")
    assert trace_id, f"Expected trace_id in response, got: {resp}"

    # Poll briefly in case DB writes are slightly delayed
    last_turns = last_tools = 0
    for _ in range(6):
        with _maybe_pg_connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM brain.turns WHERE trace_id = %s;", (trace_id,))
                last_turns = int(cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM brain.tool_calls WHERE trace_id = %s;", (trace_id,))
                last_tools = int(cur.fetchone()[0])

        if last_turns >= 2 and last_tools >= 1:
            break
        time.sleep(0.4)

    assert last_turns >= 2, f"Expected >=2 brain.turns rows for trace_id={trace_id}, got {last_turns}"
    assert last_tools >= 1, f"Expected >=1 brain.tool_calls rows for trace_id={trace_id}, got {last_tools}"
