"""
seed_from_dataset.py

First version: directly seeds Delilah's Qdrant memory with a curated
set of baseline facts about the system, user, and design.

Later we can extend this script to:
- Read from local JSON/CSV/NDJSON files
- Load Hugging Face datasets that you've downloaded locally
"""

import os
import json
import textwrap
import requests

# --------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------

# Inside the delilah_brain container, FastAPI is listening on port 8000.
# If we ever run this from the host, you can change this to:
#   BRAIN_URL = "http://192.168.1.111:8800"
BRAIN_URL = os.getenv("BRAIN_URL", "http://localhost:8000")

INGEST_ENDPOINT = f"{BRAIN_URL}/ingest"

DEFAULT_USER_ID = "system_seed"
DEFAULT_SOURCE = "seed_from_dataset_v1"

# --------------------------------------------------------------------
# SEED DATA
# --------------------------------------------------------------------
# Each item is one "fact chunk" that will be embedded and stored in Qdrant.
# Keep them 1–4 sentences so they embed cleanly.

SEED_TEXTS = [
    # Hardware & platform
    textwrap.dedent("""
    Delilah is a local AI home assistant running on a Supermicro X11SCH-LN4F
    motherboard with an Intel Xeon E-2146G CPU and 32GB of ECC RAM.
    """).strip(),
    textwrap.dedent("""
    Delilah's storage is managed by ZFS. There are three main mirrors:
    a media pool of 8TB HDDs, a documents pool of 4TB HDDs, and a fast
    delilah-pool mirror of NVMe SSDs that hosts AI data, databases, media,
    Plex configuration, and virtual machines.
    """).strip(),
    textwrap.dedent("""
    Delilah is designed to run primarily local models and services, with
    optional fallback to cloud LLMs like OpenAI, Gemini, or Claude when
    strictly necessary. The design goal is low-latency, private, local-first
    operation.
    """).strip(),

    # Core AI stack
    textwrap.dedent("""
    Delilah's AI brain stack uses Ollama for local LLMs, Qdrant as the
    vector database, a custom FastAPI service called the Delilah Brain API,
    and LangChain plus LangGraph for orchestration and tool routing.
    """).strip(),
    textwrap.dedent("""
    The main chat model currently used by Delilah is llama3:8b running via
    Ollama. Embeddings for Qdrant are also generated using the Ollama
    embedding interface with matching dimensions.
    """).strip(),
    textwrap.dedent("""
    Qdrant stores Delilah's long-term knowledge in the collection named
    'delilah_knowledge'. Additional collections are used for router hints
    and persona memory so the orchestrator can adapt routing and tone over time.
    """).strip(),

    # Tools & orchestrator
    textwrap.dedent("""
    The Delilah Brain orchestrator is built with LangGraph and can route
    user queries through different tools, including a weather tool that
    uses the U.S. National Weather Service API and a sports tool that
    queries TheSportsDB for schedules and results.
    """).strip(),
    textwrap.dedent("""
    The weather tool is optimized around Rockford, Michigan as the default
    home location, but it can also look up weather for other cities by
    geocoding user-provided place names and then calling the weather.gov API.
    """).strip(),
    textwrap.dedent("""
    The sports tool uses TheSportsDB to look up team information, upcoming
    games, and recent results. It is designed to avoid spoiling past game
    scores unless the user explicitly asks for results.
    """).strip(),
    textwrap.dedent("""
    Delilah maintains a persona memory collection that stores preferences
    about tone and style. For example, Delilah should sound warm, articulate,
    and emotionally aware, but not overly folksy or stereotypically Midwestern.
    """).strip(),

    # Mixture-of-experts & design philosophy
    textwrap.dedent("""
    Delilah's long-term architecture follows a mixture-of-experts design.
    A central orchestrator model decides when to call specialized experts
    such as coding, medical, or home automation experts, along with tools
    like weather and sports APIs.
    """).strip(),
    textwrap.dedent("""
    The system will eventually incorporate a 'jury of oracles' approach,
    where multiple LLMs or expert models produce candidate answers,
    and a critic or curator model selects or synthesizes a final response
    before any new knowledge is committed to long-term memory.
    """).strip(),
    textwrap.dedent("""
    Only vetted, relatively stable knowledge should be stored in Qdrant
    as long-term memory. Ephemeral facts like current weather, live scores,
    or stock prices should be used at answer time but not embedded as
    permanent truths in the vector database.
    """).strip(),

    # User & language preferences
    textwrap.dedent("""
    The primary user of Delilah is Ryan, who lives in the upper Midwest.
    Delilah should understand regional slang such as 'my ticker is acting up'
    meaning heart or medical problems, or 'my box is borked' referring to
    a computer or server issue.
    """).strip(),
    textwrap.dedent("""
    Delilah should speak to Ryan in a neutral, clear, and emotionally aware
    voice. She can be slightly informal and friendly, but should avoid
    sounding unintelligent or overly folksy. Empathy is important, especially
    when Ryan describes being exhausted or having a rough day.
    """).strip(),
    textwrap.dedent("""
    Automation and integration are handled through tools and external systems
    like n8n and Home Assistant. The orchestrator decides when to call these
    tools, and n8n is responsible for side-effectful workflows such as
    notifications, scheduled tasks, or device control.
    """).strip(),
]

# --------------------------------------------------------------------
# MAIN LOGIC
# --------------------------------------------------------------------

def chunk_texts(texts, max_batch_size=4):
    """Yield smaller batches so we don't send huge payloads in one go."""
    batch = []
    for t in texts:
        t = t.strip()
        if not t:
            continue
        batch.append(t)
        if len(batch) >= max_batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def main():
    print(f"[seed] Using Brain ingest endpoint: {INGEST_ENDPOINT}")
    all_inserted = 0

    for batch_num, batch in enumerate(chunk_texts(SEED_TEXTS), start=1):
        payload = {
            "texts": batch,
            "user_id": DEFAULT_USER_ID,
            "source": DEFAULT_SOURCE,
        }
        print(f"[seed] Sending batch {batch_num} with {len(batch)} text(s)...")
        try:
            resp = requests.post(INGEST_ENDPOINT, json=payload, timeout=60)
        except Exception as e:
            print(f"[seed] ERROR: request failed: {e}")
            break

        if resp.status_code != 200:
            print(f"[seed] ERROR: HTTP {resp.status_code}: {resp.text}")
            break

        try:
            data = resp.json()
        except json.JSONDecodeError:
            print(f"[seed] ERROR: could not decode JSON response: {resp.text}")
            break

        inserted = data.get("inserted", 0)
        all_inserted += inserted
        print(f"[seed] Batch {batch_num} OK: inserted={inserted}")

    print(f"[seed] Done. Total inserted across all batches: {all_inserted}")


if __name__ == "__main__":
    main()
