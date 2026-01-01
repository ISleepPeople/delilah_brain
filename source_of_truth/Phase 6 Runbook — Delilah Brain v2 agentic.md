Phase 6 Runbook — Delilah Brain v2 (Agentic-Ready, Zero Ambiguity)

Timezone: America/Detroit
Goal: Implement Phase 6 end-to-end with deterministic governance, low-debug bring-up, and a repeatable regression harness—while laying the foundations for bounded agentic behavior (Plan → Act → Verify) that can be safely expanded in Phase 7+.

0) Locked decisions (do not change during implementation)
0.1 Phase 6 scope (still true)

Phase 6 delivers: Tools, Persona-as-State v1, MoE v1 (general + coding), Cloud fallback + jury-of-oracles, Provider abstraction, Observability + regression.

Phase 6 Runbook — Delilah Brain…

Phase 6 Runbook — Delilah Brain…

0.2 Agentic blueprint constraint (new, but compatible)

Agentic behavior is allowed only as explicit, bounded orchestration:

No “free-running” autonomy. Every turn has an explicit plan envelope and hard limits.

Central policy decides what’s allowed.

Only the centralized tool executor can act. Experts may propose actions; they cannot execute them.

Phase 6 Runbook — Delilah Brain…

0.3 Corpora ingestion + governance (unchanged)

Wikipedia full ingestion; medical deferred.

Docs are version-pinned; resolver selects which docs are eligible for retrieval.

Manpages + TLDR ingested and pinned by snapshot/version.

0.4 Persona + situational style (unchanged)

Active persona state: ephemeral (in orchestrator).

Durable preferences: Postgres structured.

Style selection Option C (deterministic rules + bounded LLM realization).

0.5 MoE v1 (unchanged)

Experts: general + coding.

Routing: rules-first + LLM tie-breaker only when inconclusive.

Retrieval: strict per-expert allowlists.

Tools: tool-intents bypass RAG; centralized execution only.

Phase 6 Runbook — Delilah Brain…

0.6 Cloud fallback + jury-of-oracles (unchanged)

Controlled automatic fallback (policy-gated), parallel race (OpenAI+Gemini), async jury (Claude) via n8n.

Write-back only to curated collection with strict gates.

0.7 Provider abstraction + observability (unchanged)

Thin provider interface with streaming day one.

Full structured trace record per turn in Postgres. 

Phase 6 Runbook — Delilah Brain…

1) Prerequisites and “do not proceed unless” checks
1.1 Repo and source-of-truth layout

Ensure the repo contains:

source_of_truth/

PROJECT_STATE.md

ARCHETECTURAL_DECISIONS.md

RULES.md

README_LLM.md

phase6_runbook.md (this doc)

versions_manifest.yml (resolver fallback)

infra/ (compose/networks/volumes)

brain/ (FastAPI + orchestrator)

tools/ (registry + executor + contracts)

corpora/ (pipelines + manifests)

providers/ (Ollama/OpenAI/Gemini/Claude adapters)

policy/ (central policy module)

tests/phase6/ (regression harness)

NEW (agentic-ready): agents/ (bounded plan/execution contracts + tests)

1.2 Services assumed available (current state)

Qdrant running and reachable from Brain containers

Brain API v2 compose prepared

Postgres available (system-of-record) or stood up in Phase 6.6 if missing

1.3 “Stop if failing” rule

At each phase step:

apply exactly one change

run verification

if verification fails: stop, fix, re-verify

only then proceed

2) Phase 6.0 — Guardrails and Regression Harness (build first)
2.1 Implement central policy module

Create policy/ with deterministic functions and typed outputs:

Required (existing):

classify_intent(request) -> intent (tool | knowledge | mixed)

classify_volatility(request) -> stable | volatile

redact_for_cloud(text) -> redacted_text + redaction_report

decide_routing(request) -> RoutingPlan

decide_style(request, memory, prefs) -> StyleDecision

decide_retrieval(intent, volatility, expert, corpora_state) -> RetrievalPlan

NEW (agentic-ready):

decide_agent_mode(request, intent) -> AgentModeDecision

mode = SINGLE_SHOT | BOUNDED_PLAN (default SINGLE_SHOT until Phase 6.3 verification is solid)

decide_action_budget(intent, tool_risk) -> ActionBudget

e.g., max_steps, max_tool_calls, max_retrieval_calls, max_seconds

classify_tool_risk(tool_name) -> READ_ONLY | MUTATING

require_confirmation(tool_risk, user_intent) -> bool (Phase 6 default: true for mutating unless request is explicit and allowlisted)

### 2.1A Clarification Gate (First-Class Node)

Objective
Make “ask for missing information” deterministic and testable, instead of ad-hoc model behavior.

Policy Additions
Implement:
- detect_missing_slots(request, routing_plan) -> MissingSlots
- build_clarifying_question(missing_slots) -> ClarifyingPrompt
- decide_clarification(required_slots, confidence, ambiguity) -> ClarificationDecision

Rules
- If required slots are missing for a tool/expert path, return NEEDS_MORE_INPUT with:
  - required_slots[]
  - one concrete clarifying question
  - a minimal “what to paste” instruction (e.g., exact command output)

Acceptance Criteria
- For known missing-slot prompts (repo unknown, host unknown, missing logs), system returns NEEDS_MORE_INPUT deterministically.
- Regression tests exist for at least 10 clarification cases (coding + ops + general).

2.2 Build regression harness (golden tests + invariants)

Create tests that enforce:

policy decisions deterministic given same inputs

invariants always hold (volatile facts never stored; tool calls auditable; tool-intents bypass RAG)

style contract is always produced and never violates bounds

routing is rules-first with tie-breaker only when inconclusive

NEW (agentic-ready): golden “plan traces”
Add a small set of scenario tests that validate planning output even before you allow multi-step execution:

given a stack trace → plan includes “identify subsystem → choose diagnostics tool(s) → propose patch steps” (tools may be “dry run” initially)

given a “how do I fix X” → plan includes retrieval first, then propose commands, then verify step

### 2.2A Agentic RAG Regression Cases (Minimum Set)

Add the following golden scenarios to tests/phase6/:

1) Clarification Gate
- Missing repo/log/host → MUST return NEEDS_MORE_INPUT with required_slots + concrete ask.

2) Retrieval Sufficiency Evaluator
- Known-good retrieval → SUFFICIENT
- Known-bad retrieval → INSUFFICIENT with reason_codes

3) Hierarchical Metadata
- Parent/child chunks present and queryable by chunk_level filter.

4) Loop Budget Enforcement (when enabled)
- Retrieval loop never exceeds max_retrieval_passes and terminates deterministically.

5) Trace Integrity
- Every step writes trace_id; if subtasks planned, subtask telemetry is present.


2.3 Verification (must pass)

Run the test suite locally (container/venv).

Confirm failures are deterministic.

Confirm policy can deterministically deny a disallowed action.

3) Phase 6.1 — Tool framework expansion + centralized execution
3.1 Implement tool contract and registry

Create:

tools/contract.py: ToolRequest, ToolResult

tools/registry.py: names, schemas, permission tags, risk level, allowlists

tools/executor.py: single executor that

validates inputs

consults policy allow/deny

executes tool

logs tool audit (Phase 6.6)

returns normalized result (never crashes orchestration)

3.2 Verification (framework)

Add a “dry-run tool” that performs no external action but returns a structured response.

Confirm:

tool calls produce audit entries

policy can block calls deterministically

3.3 Tool APIs v1 (implement now; defer expansion to Phase 7)

Purpose: validate end-to-end governed tool pathway (policy → tool request → centralized executor → audit log → structured result) with minimal, low-risk tools:

Tool APIs v1:

system.health_check

Brain API, Qdrant, Postgres, n8n endpoints

structured per-service health: ok, latency_ms, error

system.get_versions

reads running container image tags/digests/labels

feeds Docs Version Resolver as truth source

system.snapshot_capture

executes fixed “small but comprehensive” command set

writes timestamped bundle to corpora cache and ingests it

mqtt.publish

publish-only

strict allowlist topics (explicit list in config)

payload size limit

block wildcards and retained messages unless explicitly allowed

audited (topic, payload hash, ok/fail, duration)

Tool framework requirements (non-negotiable):

Tools executed only by centralized executor (experts never execute tools directly)

Every call has trace_id

Every tool call writes an audit row in Postgres (Phase 6.6)

Phase 6 Runbook — Delilah Brain…

3.4 NEW (agentic-ready): ToolRequest extensions (still compatible)

Extend ToolRequest (no behavior changes yet) to support agentic planning:

purpose: one-line intent (“collect diagnostics”, “verify service health”)

risk_level: READ_ONLY | MUTATING (from registry)

idempotency_key: required for mutating tools (prevents duplicates)

dry_run: optional (Phase 6 default true for mutating tools unless explicitly allowed)

expected_effects: human-readable (for trace + later UX)

3.5 Verification (must pass before proceeding to Phase 6.1.x)

Run each Tool API v1 once and confirm:

policy gating works (deny test for disallowed MQTT topic)

tool audit entries are written

ToolResult envelopes are normalized and stable

Phase 6 Runbook — Delilah Brain…

Phase 7 note (defer):

Expand tool catalog later (Home Assistant, media, device ops) using same contract + executor + audit.

4) Phase 6.1.x — Baseline Corpora Ingestion (Wikipedia + DevOps + Troubleshooting)
4.1 Corpora cache and manifests (mandatory)

Create a ZFS dataset/location dedicated to corpora snapshots and manifests (if not already). Every ingestion run must:

use snapshot IDs in names

store a manifest containing:

corpus name + snapshot date

source identity

pipeline version

chunking settings

embedding model identity (unchanged)

deterministic ID strategy

provenance payload schema

### 4.1A Hierarchical Retrieval Metadata (Parent/Child Chunks) — Scaffolding

Objective
Introduce hierarchical indexing support (child chunks for retrieval precision; parent chunks for synthesis context), without changing baseline retrieval behavior unless feature-flagged.

Implementation (Ingestion-Time Only in Phase 6)
All corpora pipelines MUST support emitting two levels of chunks:
- child_chunk: small, high-precision retrieval units
- parent_chunk: larger “context carriers” that group related child chunks

Required metadata fields on every vector record (Qdrant payload):
- chunk_level: "child" | "parent"
- parent_id: stable ID of the parent chunk (required for child)
- child_ids: optional list of children (optional for parent)
- source_doc_id: stable doc identifier
- source_path / uri (if applicable)
- chunk_index, chunk_hash
- snapshot_id (corpus snapshot provenance)
- version_id (pipeline version provenance)

Feature Flag
- HIERARCHICAL_RAG_ENABLED=false (default in Phase 6)
- When false, retrieval behaves exactly as baseline (single-level retrieval).
- When true (Phase 7+), retrieval returns child chunks but expands to parents for synthesis.

Acceptance Criteria (Phase 6)
- Ingestion pipelines can produce parent/child metadata deterministically.
- Retrieval queries can filter by chunk_level="child" without errors.
- No runtime behavior changes occur unless HIERARCHICAL_RAG_ENABLED=true.


4.2 Wikipedia baseline ingestion (full)

Create Qdrant collection: baseline_wikipedia_en_<YYYYMMDD>

Set active pointer: COL_WIKI_BASELINE=baseline_wikipedia_en_<YYYYMMDD>

Execute: stage dump → transform → normalize → chunk → embed → upsert

Verify: small known-query suite; confirm retrieval latency within bounds

4.3 DevOps baseline ingestion (manpages + TLDR)

Manpages:

source: /usr/share/man (+ configured man paths)

normalize → chunk → embed → upsert with deterministic IDs

TLDR:

snapshot TLDR sources to corpora cache

normalize → chunk → embed → upsert

Verify: queries return expected content quickly and consistently

4.4 Stack Docs Pack v1 (official docs snapshots + version scoping)

Define doc sources (explicit scope)

Create version-pinned collections

Implement docs extraction pipeline (HTML/PDF snapshots → text extraction → chunk → embed)

Docs Registry in Postgres (authoritative) + export read-only snapshot YAML committed to Git

Docs Version Resolver (version-scoped retrieval)

Retention policy (compat pins + LRU; prune non-pinned not used in 120 days)

Verify resolver selects only eligible doc snapshots

4.5 Troubleshooting Corpus v1 (runbooks + known-good snapshots)

Create collections

Ingest runbooks

Implement known-good snapshot capture CLI (manual)

Verify snapshot capture ingests bundles and queries return captured outputs + timestamps

5) Phase 6.2 — Persona v1 + situational style (Option C)
5.1 Postgres tables for persona preferences

Structured storage for durable preferences

Persona state remains ephemeral per turn

5.2 StyleDecision contract (Option C)

Every turn must produce a StyleDecision:

selected_style (neutral/helpful, joking, comforting, dry, etc.)

intensity bounded

allowed/disallowed styles

reason codes

trace_id

LLM does not choose style; it realizes selected style within constraints

5.3 Verification

regression tests pass for style contract

style never violates disallowed constraints

no coupling to TTS required

6) Phase 6.3 — MoE v1 (general + coding)
6.1 Expert registry

Implement ExpertSpec for:

general

coding

6.2 Routing (rules-first + tie-breaker)

Coding intent detector: multi-signal (examples):

code blocks, stack traces, compiler errors

file paths / repo structure mentions

build tooling (docker, compose, systemd, logs, etc.)

Tie-breaker LLM only when classifier is inconclusive.

6.3 Retrieval allowlists

Each expert has strict allowlists of Qdrant collections it may query.

### 6.3A Retrieval Sufficiency Evaluation (Bounded Loop) — Feature-Flagged

Objective
Enable an agentic retrieval loop: retrieve → evaluate sufficiency → optionally refine query → retrieve again, within strict budgets.

Feature Flag
- RETRIEVAL_LOOP_ENABLED=false (default in Phase 6)

Implementation
Add a RetrievalEvaluator that consumes:
- the user query
- the retrieval results (top-k snippets + metadata)
- expert_id (general/coding)
and outputs:
- sufficiency: SUFFICIENT | INSUFFICIENT
- reason_codes[] (e.g., "low_relevance", "no_authoritative_source", "missing_version")
- refinement_hint (optional short string)
- recommended_next_action: CLARIFY | RETRIEVE_AGAIN | PROCEED_WITH_CAUTION

Bounded Policy
If RETRIEVAL_LOOP_ENABLED=true:
- max_retrieval_passes = 2 (Phase 7 may increase)
- second pass may adjust query using refinement_hint, but must remain within allowlisted corpora.
- if still insufficient, return NEEDS_MORE_INPUT or proceed with explicit uncertainty.

Acceptance Criteria (Phase 6)
- Evaluator exists and returns stable outputs for a fixed test suite.
- When disabled (default), behavior is unchanged.
- When enabled, loop never exceeds budget and always terminates deterministically.

6.4 Tools

Tool-intents hard bypass RAG

Experts may propose tool actions but never execute tools directly; executor is centralized

6.5 Expert output format

Require structured ExpertResult + answer text.

6.6 NEW (agentic-ready): “BoundedPlan” output (optional in Phase 6)

Allow experts (especially coding) to optionally include a proposed plan:

ProposedPlan.steps[] where each step is:

step_type: RETRIEVE | TOOL | LLM_SUMMARY | VERIFY

tool_name (if TOOL) + args schema reference

success_criteria (what to check next)

risk_level (from tool registry; must match)
This is not autonomous execution yet; it’s a structured proposal the orchestrator can accept/reject.

6.7 Verification

coding prompts route to coding expert

tool prompts bypass retrieval and hit tool executor

retrieval touches only allowlisted collections

if ProposedPlan is present: policy can accept/deny steps deterministically; trace records include plan

7) Phase 6.4 — Controlled cloud fallback (parallel race + async jury)
7.1 Eligibility gates (hard requirements)

Cloud fallback allowed only when all true:

intent ≠ tool

volatility classification applied

local sufficiency insufficient (retrieval poor or confidence low)

privacy redaction/minimization succeeds

7.2 Synchronous parallel race (streaming, early accept)

Locked participants and acceptance policy remain as specified in the runbook.

7.3 Asynchronous jury-of-oracles (n8n)

n8n fan-out to Claude as third opinion

returns curated candidate + metadata for curator gate

7.4 Write-back policy (strict)

write-back goes only to curated_cloud_knowledge with stability + consensus + curator gates

never store volatile facts

7.5 Retrieval priority

Wikipedia baseline first

curated cloud knowledge second (supplemental)

other allowlisted corpora per expert rules

7.6 Verification

force a known “gap” query

confirm race behavior and acceptance logic

confirm write-back gating works and stores only curated results

8) Phase 6.5 — Provider abstraction (adapters + streaming)
8.1 Provider Interface (thin adapter)

All LLM calls must go through:

generate()

stream_generate()

Required adapters:

Ollama (local)

OpenAI (cloud race)

Gemini (cloud race)

Claude (async jury via n8n path; provider still exists for uniform envelope if needed)

Provider response must include:

token usage (future cost tracking)

trace_id propagation

normalized envelope fields

### 8.1A Provider Abstraction — Acceptance Checklist (vLLM-Ready)

Objective
Phase 6.5 is “vLLM-ready” when adding a new local runtime (e.g., vLLM OpenAI-compatible server) requires only:
- a new provider adapter + configuration
- zero changes to orchestration logic, routing logic, tool executor logic, or policy logic
- passing the same regression harness and invariants

Non-Negotiable Deliverables (must exist by end of Phase 6.5)

A) Canonical Provider Contract (Request/Response Envelope)
Provider Interface MUST standardize:
- Inputs:
  - messages (canonical internal message type)
  - tools (canonical internal tool schema type)
  - response_schema (optional structured output schema, if used)
  - stream (bool)
  - metadata including trace_id
- Outputs (normalized envelope, provider-agnostic):
  - assistant_text (string)
  - tool_calls[] (canonical internal tool-call representation; never provider-native raw)
  - usage (tokens, latency if available)
  - model_id / provider_id
  - trace_id (propagated)
- Errors:
  - canonical error types (timeout, rate_limit, invalid_output, provider_unavailable, auth, unknown)
  - retryable flag + recommended backoff hints (optional)

Acceptance criteria:
- No code outside providers/ is allowed to depend on provider-specific response shapes.
- Tool calls are always normalized into the same internal representation before use.
- Provider adapters MUST normalize provider-native tool call formats into the canonical internal ToolCall schema; the orchestrator and tool executor must never consume provider-native tool-call payloads directly.

B) Mock Provider for Deterministic Testing
Implement a “mock provider” used by tests that can:
- return deterministic assistant text
- return deterministic tool_calls payloads
- simulate streaming token events
- simulate provider errors (timeout, invalid output)

Acceptance criteria:
- The regression harness can run end-to-end without any external network calls.
- Tool execution and auditing can be validated against deterministic provider outputs.

C) Provider-Agnostic Tool Calling + Structured Output Tests
Add regression tests that enforce:
- Tool-call outputs validate against the tool schema (JSON validity + schema compliance)
- Invalid tool-call output triggers the repair/retry path (bounded retries) OR a safe “NEEDS_MORE_INPUT” result
- Provider switching does not alter tool routing invariants (tool-intent bypasses RAG, etc.)
- Streaming works for at least one provider implementation with consistent event envelope

Acceptance criteria:
- JSON validity rate for tool calls is effectively 100% under test conditions (invalid outputs are corrected or rejected deterministically).
- Tool-call parsing does not vary by provider.

D) Per-Expert Provider Selection (Config Shape Exists Now)
Even if all experts still point to the same backend today, configuration MUST support per-expert provider selection:
- EXPERT_GENERAL_PROVIDER=...
- EXPERT_CODING_PROVIDER=...
- (optional) EXPERT_ROUTER_PROVIDER=...
- (optional) EXPERT_CRITIC_PROVIDER=...

Acceptance criteria:
- The orchestrator selects providers strictly via config (no hard-coded backend assumptions).
- Swapping an expert from “ollama” to “vllm” later is a config-only change.

E) “Deferred but Pre-Wired” vLLM Integration Plan (No Deployment Required in Phase 6)
Phase 6 must include an explicit, tested path for adding vLLM later, without implementing it yet.

Required artifacts (placeholders/scaffolding):
- A provider stub entry: provider_id = "vllm" (disabled by default)
- Documentation for how to enable vLLM by adding:
  1) a vLLM service stanza in infra compose (profile: gpu)
  2) a provider endpoint URL/env var
  3) expert-to-provider mapping (config)
- Standard health-check pattern for any local provider service (consistent with other services)
- Standard network attachment pattern used by all inference runtimes

Acceptance criteria:
- “Add vLLM” later is reduced to:
  1) deploy vLLM container (new service)
  2) enable vllm provider adapter + URL
  3) switch one expert to vLLM via config
  4) run regression harness
  5) canary + cutover

Future vLLM Cutover Steps (explicit procedure)
When vLLM is introduced in Phase 7+:
1) Deploy vLLM alongside existing local runtime (do not remove existing runtime).
2) Enable vllm provider adapter and health checks (provider=vllm remains opt-in).
3) Canary route a single expert first (recommended: coding expert) via config only.
4) Validate:
   - tool-call schema compliance
   - latency envelope
   - regression suite + invariants
5) Expand routing and finally flip defaults if desired (config-only changes).

Definition of Done for Phase 6.5
Phase 6.5 is complete when A–E are implemented and all acceptance criteria pass, including:
- provider contract locked and used everywhere
- mock provider tests pass
- tool-call schema tests pass
- per-expert provider selection is config-driven
- vLLM integration path is documented and pre-wired (but not deployed)


8.2 Verification

run a local request via provider interface

run OpenAI/Gemini race via provider interface using streaming

confirm consistent output envelopes

9) Phase 6.6 — Observability (Postgres ledger + audits) and final hardening
9.1 Postgres schema: turn ledger + tool audit + fallback audit

Mandatory fields per turn:

trace_id, timestamp, user_id

intent, volatility

expert_id and reason codes

StyleDecision summary

retrieval metadata (collections, thresholds, top-k summary)

tool audit rows (tool name, args hash, result hash, duration, ok/fail)

fallback race (participants, winner, acceptance signals)

write-back info (collection, consensus score, curator version)

NEW (agentic-ready): plan + step telemetry
If a plan exists (even if not executed autonomously):

store plan_json (or plan hash + blob table)

store step_events[] if any steps executed (ordered, with timestamps and success/failure)

store action_budget used for the turn (max steps/calls/time)

### 9.1A Parallel Sub-Query Telemetry (Map-Reduce Ready)

Objective
Prepare for Phase 7+ parallel decomposition (map-reduce) by defining trace structures now.

Schema Requirements (Phase 6)
If the orchestrator generates sub-queries (even if not executed in parallel yet), record:
- parent_trace_id
- subtask_id (stable)
- subtask_query
- assigned_expert_id
- retrieval_collections_used
- subtask_status (planned | executed | skipped)
- subtask_result_hash (optional)

Acceptance Criteria
- Trace schema supports N subtasks per user turn.
- Subtask metadata is queryable for debugging and future training (router + decomposition).


9.2 Verification

Every request produces:

a complete ledger row

tool audit rows if tools executed

fallback audit rows if cloud fallback executed

if plan present: plan recorded and policy decisions explainable

10) Phase 6 completion checklist (definition of “done”)

Phase 6 is complete when all are true:

Central policy module exists and is used everywhere

Regression harness passes and includes golden tests + invariants

Corpora ingestion is live:

Wikipedia baseline active

manpages + TLDR active

Stack Docs Pack active and version-scoped by resolver + registry

troubleshooting corpus and snapshot capture CLI active

Tool framework is live:

Tool APIs v1 implemented

centralized executor enforced

policy gating enforced

tool audits written to Postgres

Persona v1 is live:

Postgres preferences tables

StyleDecision contract always produced; bounded

MoE v1 is live:

general + coding experts

rules-first routing

strict retrieval allowlists

tool-intents bypass retrieval

Cloud fallback is live:

eligibility gates enforced

parallel race behavior correct

async jury workflow works

write-back gates enforced to curated collection only

Provider abstraction is live and used everywhere

Observability is complete:

per-turn ledger is complete

tool/fallback audits correct

agentic-ready telemetry present (plan capture + step events even if bounded plan execution is feature-flagged)

Outputs that must exist and be committed/read-only where stated:

docs_registry.snapshot.yml exported from Postgres

phase6_runbook.md (this doc)

Appendix — Explicit “future” items not in Phase 6

Expanded tool catalog (Home Assistant actions, media control, device ops) beyond Tool APIs v1

Fully autonomous multi-turn workflows (continuous loops) and long-horizon task execution

Persona exemplars semantic store (curated Qdrant collection)