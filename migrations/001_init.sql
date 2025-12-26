-- Delilah Brain v2
-- Initial schema for structured state (system of record)

BEGIN;

CREATE SCHEMA IF NOT EXISTS brain;

-- Canonical conversation / turn ledger
CREATE TABLE IF NOT EXISTS brain.turns (
  turn_id UUID PRIMARY KEY,
  trace_id UUID NOT NULL,
  user_id TEXT NOT NULL,
  role TEXT CHECK (role IN ('user','assistant')) NOT NULL,
  text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  used_context BOOLEAN,
  used_conversation_context BOOLEAN,
  num_docs INTEGER,
  target_expert TEXT,

  tool TEXT,
  latency_ms INTEGER,

  meta JSONB
);

CREATE INDEX IF NOT EXISTS idx_turns_trace_id
  ON brain.turns (trace_id);

CREATE INDEX IF NOT EXISTS idx_turns_user_time
  ON brain.turns (user_id, created_at);

-- Tool execution audit log
CREATE TABLE IF NOT EXISTS brain.tool_calls (
  tool_call_id UUID PRIMARY KEY,
  trace_id UUID NOT NULL,
  user_id TEXT NOT NULL,

  tool TEXT NOT NULL,
  args JSONB,
  result JSONB,
  error TEXT,

  started_at TIMESTAMPTZ NOT NULL,
  ended_at TIMESTAMPTZ,
  latency_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_trace_id
  ON brain.tool_calls (trace_id);

COMMIT;
