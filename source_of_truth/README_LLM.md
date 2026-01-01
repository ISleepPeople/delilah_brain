Project: Delilah

Delilah is a policy-governed, auditable, tool-using agentic system designed to operate reliably without cloud dependence (local-first), while allowing explicitly gated cloud fallback when required.


“Agentic” means Delilah can plan, take governed tool actions, verify outcomes, and iterate—within explicit limits and with full auditability.

The system integrates:

Deterministic orchestration (explicit state, not emergent behavior)
Bounded agent loops (Plan → Act → Verify)
Structured system-of-record logging (PostgreSQL)
Semantic memory (RAG) with strict persistence policies
Centralized tool execution with auditing and policy gating
Mixture-of-Experts (MoE) routing (planned)
Voice and home automation interfaces (planned)


This project prioritizes:

Determinism over novelty

Explicit architecture over implicit behavior

Incremental phases with frozen, verifiable baselines

Observability, auditability, and long-term maintainability

No silent failures, no hidden state

Agentic Definition (Canonical)

Delilah is “agentic” in the specific sense that it can plan and execute multi-step work by invoking tools (APIs, automations, Home Assistant actions) under strict policy gates.

Agentic does NOT mean uncontrolled autonomy:
- Tool execution is explicit and policy-governed.
- All actions are traceable (trace_id) and auditable (tool-call records).
- Memory writes are intentional; volatile facts are never persisted.
- PostgreSQL remains the system of record; Qdrant is semantic recall only.


Snapshot Context

Snapshot date: December 2025

Host: Supermicro X11SCH-LN4F

Xeon E-2146G

32 GB ECC RAM

OS: Ubuntu Server

Storage: ZFS with dedicated datasets per workload

Runtime: Docker / Docker Compose

GPU: RTX 3060 12 GB (active; future GPU planned)

This repository reflects a known-working, tagged baseline:
Delilah Brain v2 (post-hardening, pre-Phase 6).

Current System State (Authoritative Truth)
✅ Verified Working
Core Runtime

Delilah Brain v2

FastAPI service

Stable on port :8800

Endpoints:

/ask

/ingest

/health

/health/deps

Docker Compose

Clean startup

No restart loops

Dependency-aware health checks

Data & Memory

PostgreSQL (System of Record)

Turn ledger

Tool call audit log

Trace IDs

Authoritative history

Qdrant

Semantic memory only

Embedding dimension: 768

No authoritative state

Strict persistence policy

Volatile data (weather, sports, prices) is never persisted

Tool calls are auditable but selectively excluded by policy

Tooling & Automation

Weather tool

Enabled

Tool-only execution

No RAG context

No Postgres or Qdrant persistence

n8n

Webhook-based ingestion

Automation glue (not reasoning)

Structured JSON logging

Timeout-guarded execution (no hangs)

Operations & Hardening

Automated PostgreSQL backups with retention

Restore-tested backups

Dedicated ZFS dataset for backups

Hourly ZFS snapshots for authoritative datasets

Startup configuration logging via FastAPI lifespan hook

Make-based verification and smoke test harness

Current Baseline Guarantees

The following are guaranteed invariants of the system:

PostgreSQL is the only system of record

Qdrant is semantic recall only

Tools do not implicitly write memory

Volatile information is never stored

RAG is explicitly gated

All tool executions are traceable

Rollback is always possible (Git + ZFS + DB backups)

🚫 Not Yet Implemented (Explicitly)

LangGraph orchestration graph

Mixture-of-Experts routing

Multiple expert-specific RAG collections

Jury-of-Oracles cloud fallback

Persona-as-state (beyond minimal scaffolding)

OVOS / HiveMind satellites

Speaker recognition

Expressive TTS runtime layer

Home Assistant command execution loop

These are planned and will be introduced incrementally starting in Phase 6.

Architectural Intent (Do Not Deviate)

Delilah follows a layered control architecture:

User
↓
(Future) Voice / UI Interface
↓
Brain Orchestrator (Brain v2 → future LangGraph)
↓
├─ Local LLM Runtime (Ollama)
├─ Tool Layer (Weather, APIs, automations)
├─ Qdrant (semantic memory / RAG)
├─ PostgreSQL (system of record)
├─ n8n (workflow orchestration)
└─ Home Assistant (actuation)

Core Principles

LLMs are tools, not the brain

Reasoning is explicit, not emergent

Memory writes are intentional, not accidental

Agentic actions are explicit, bounded, and verified (no free-running autonomy)

Voice artifacts are added at runtime, never baked into training

Infrastructure changes must not break a working baseline

Hard Constraints (Must Always Be Respected)

Local-first operation is preferred

Cloud APIs are optional and explicitly gated

Cloud fallback is logged and auditable

Fallback results are candidates for curation, not truth

Existing verified pipelines must not be broken

ZFS dataset layout is intentional

Python version pinning matters

Docker services are additive, not destructive

Configuration must be reproducible and versioned

Decisions Already Made (Do Not Re-litigate)
Adopted

PostgreSQL as system of record

Qdrant for embeddings and recall only

Docker-first deployment

Dedicated ZFS datasets per workload

Modular service composition

Future MoE + RAG architecture

Clean TTS training data (no breaths, clicks, mouth noise)

Explicitly Rejected

Stateless conversation design

Cloud-only assistants

Monolithic assistant processes

Baking expressiveness into TTS training

Silent architectural changes

Implicit assumptions about hardware, APIs, or persistence

What an LLM Is Allowed to Do

Propose new services alongside existing ones

Suggest phased, reversible migrations

Improve observability, safety, and documentation

Introduce tools and policies with verification steps

Ask clarifying questions before refactors

What an LLM Must NOT Do

Delete or refactor working services without instruction

Replace PostgreSQL or Qdrant roles

Collapse services into a monolith

Assume cloud services exist

“Simplify” by removing architectural layers

Ignore stated constraints, rules, or decisions

Phase Roadmap (High Level)

Phase 5: Hardening & baseline stabilization ✅

Phase 6: Tools, Persona-as-State, MoE routing, Cloud fallback

Phase 7+: Voice, automation, multimodal memory, serving upgrades

Repository Navigation Guide

/docker/ – Compose files and service definitions

/configs/ – Versioned runtime configuration

/scripts/ – Operational and maintenance scripts

/docs/ – Deep-dive technical notes

/migrations/ – PostgreSQL schema migrations

Final Instruction to LLMs

If a behavior, assumption, or dependency is not written in this file,
do not assume it exists.

When in doubt:

Ask

Propose

Phase

Do not break working state

End of File