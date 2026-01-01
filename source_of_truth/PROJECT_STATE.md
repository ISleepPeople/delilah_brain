Project State Snapshot — Delilah
Snapshot Metadata (Authoritative)

Snapshot date: December 2025

State label: WORKING_BRAIN_V2_BASELINE_PRE_PHASE_6

Phase: Pre-Phase 6 (Foundation Hardened)

Intended audience: Humans and LLMs resuming work

Confidence level: High — system verified operational

Change policy: Additive changes only unless explicitly authorized

This snapshot represents a known-good, tagged, and verified baseline of Delilah Brain v2.
All future development must preserve the guarantees described here.

System Summary (Ground Truth)

Delilah is currently operating as a local-first, policy-governed, auditable, tool-using agentic system — currently in a constrained baseline mode — with:

A single active Brain v2 service

Explicit separation between:

System of record (PostgreSQL)

Semantic memory (Qdrant)

Tools / real-time APIs (non-persistent)

Hardened infrastructure with rollback, backups, and observability

No voice, automation, or MoE features are active yet. This is intentional.

This snapshot is a “safe agentic foundation”: auditability, strict persistence rules, and tool gating are in place, but autonomous multi-step task execution is not yet enabled.

Strategic Goal (North Star)

Delilah’s long-term goal is to become a fully functioning agentic AI system: it will plan, execute governed tool actions, verify results, and iterate safely.

This snapshot is pre-agentic by design (foundation hardened). Agentic behavior will be introduced incrementally starting in Phase 6 via:
- Central policy + regression harness
- Centralized tool executor + tool contracts
- MoE routing (general + coding first)
- Plan → Act → Verify loop scaffolding with bounded budgets and verification gates


Runtime Verification (True at Snapshot Time)
Docker & Process Health

docker compose up -d completes without errors

All declared services reach running / healthy state

No crash loops or restart storms

No orphan containers

Networking & Ports
Service	Port	Status	Notes
delilah_brain_v2	8800	Reachable	FastAPI
qdrant	6333	Reachable	768-dim embeddings
n8n	5678	Reachable	Workflow automation
delilah_postgres	5432	Reachable	Separate infra compose
ollama	11434	Reachable	Docker DNS

Networking model

Docker network: delilah_net

AI services communicate via Docker DNS

PostgreSQL accessed via host.docker.internal (intentional isolation)

No port conflicts

Data & Memory Responsibilities (Strict)
PostgreSQL — System of Record

Schema: brain

Tables:

brain.turns

brain.tool_calls

Stored

Conversation turn ledger

Tool call audit entries (with trace IDs)

Deterministic system history

Explicitly NOT stored (by policy)

Weather data

Sports scores

Prices

Real-time or ephemeral tool outputs

PostgreSQL is the authoritative history of the system.

Qdrant — Semantic Memory Only

Embedding dimension: 768

Collections:

delilah_knowledge

Used for

Knowledge retrieval (RAG)

Long-term semantic memory

Not used for

Weather

Sports

Real-time tools

Transient responses

Qdrant is never a system of record.

Tools & APIs
Weather Tool (weather.gov)

Status: ✅ Fully operational

Uses:

OpenStreetMap Nominatim (geocoding)

api.weather.gov/points

forecast endpoint

Makes real HTTP requests

Tool-only execution:

❌ No RAG context

❌ No PostgreSQL persistence

❌ No Qdrant writes

Output verified safe (ASCII-safe)

This tool is the reference implementation for volatile, non-persistent tools.

Verified Functional Tests

The following have been explicitly tested and verified:

GET /health

GET /health/deps

POST /ask

POST /ingest

Tool execution and audit logging

Trace ID propagation

Structured JSON logging

Startup configuration logging (FastAPI lifespan)

Memory & Persistence

Qdrant ingestion and retrieval works

PostgreSQL schema verified

Tool exclusion rules verified (weather not logged)

Operations & Hardening

Automated PostgreSQL backups enabled

Backup retention configured

Restore tested successfully

Dedicated ZFS dataset for backups

Hourly ZFS snapshots for authoritative datasets

No data stored in ephemeral container layers

Git repository initialized and tagged at baseline

Explicitly Not Implemented (Not Defects)

The following are intentionally absent at this snapshot:

LangGraph orchestration

Mixture-of-Experts routing

Expert-specific RAG collections

Cloud fallback / jury-of-oracles

Persona-as-state (beyond minimal scaffolding)

OVOS / HiveMind

Speaker identification

Expressive TTS runtime layer

Home Assistant command execution

These will be introduced starting in Phase 6.

Known Limitations (Accepted)

Single Qdrant collection

Minimal orchestration logic

No automated freshness re-validation

No request prioritization or concurrency tuning

These are acceptable at this stage and do not represent instability.

Last Known Safe Point

Git tag: delilah-brain-v2-baseline-2025-12-26

Expected behavior if restored:

Text-based conversation works

Memory ingestion functions

Tool execution works with audit logging

No voice or automation actions occur

Recovery Instructions (If Drift Is Suspected)

Stop all containers

Restore last known safe Git tag

Restore PostgreSQL from last verified backup (if needed)

Verify Qdrant collection presence

Run verification harness (make verify, make smoke)

Do not proceed until all checks pass

Forward Progress Guidance

All future development must follow:

Mode-segregated work (Planning / Implementation / Diagnostics)

One change → verification → next change

Feature flags for new behavior

Snapshot updates after each phase milestone

Final Instruction

This file defines the ground truth of Delilah at this point in time.

If observed behavior differs from what is written here,
the system is no longer in this snapshot state and must be re-verified.