"""
seed_more_knowledge.py

Additional curated baseline facts to feed into Qdrant so Delilah
has a richer self-concept and system knowledge.

This does NOT replace the earlier seeder; it just adds more chunks.
"""

import os
import json
import textwrap
import requests

BRAIN_URL = os.getenv("BRAIN_URL", "http://localhost:8000")
INGEST_ENDPOINT = f"{BRAIN_URL}/ingest"

DEFAULT_USER_ID = "system_seed"
DEFAULT_SOURCE = "seed_more_knowledge_v1"

MORE_TEXTS = [
    # OVOS / HiveMind / voice layer
    textwrap.dedent("""
    Delilah's voice interface will be built on Open Voice OS (OVOS)
    and HiveMind. OVOS Core handles skills and conversation flows,
    OVOS Audio manages playback and microphones, and HiveMind lets
    lightweight satellite devices forward audio and intents to the
    main brain running on the server.
    """).strip(),
    textwrap.dedent("""
    Wyoming-based services provide speech components for Delilah.
    Whisper or Faster-Whisper handle speech-to-text (STT), Piper
    handles text-to-speech (TTS), and Silero VAD is used to detect
    when someone is speaking. These services run next to OVOS and
    communicate over simple TCP protocols.
    """).strip(),
    textwrap.dedent("""
    The long-term goal is to have a dedicated kiosk or satellite
    device acting as the main 'face' of Delilah, with microphones,
    speakers, and a small display, while the heavy AI models and
    vector database continue to run on the main Delilah server.
    """).strip(),

    # Home Assistant + automation
    textwrap.dedent("""
    Home Assistant will be used as the central home automation hub.
    Delilah should eventually be able to control lights, sensors,
    media devices, and other smart home equipment by sending
    structured commands to Home Assistant, instead of directly
    manipulating devices herself.
    """).strip(),
    textwrap.dedent("""
    n8n is the main automation and glue engine in Delilah's design.
    It is responsible for workflows like notifications, scheduled
    summaries, and multi-step sequences that combine APIs such as
    weather, sports, and Home Assistant events.
    """).strip(),
    textwrap.dedent("""
    The Delilah Brain API exposes a simple HTTP interface for
    ingestion and querying. Other systems such as n8n, OVOS, or
    Home Assistant can send POST requests to /ingest to store new
    memories, and POST to /ask to retrieve contextual answers.
    """).strip(),

    # Mixture-of-experts / routing / hints
    textwrap.dedent("""
    Router hints are stored in a dedicated Qdrant collection so
    the orchestrator can learn how user language maps to specific
    experts or tools. For example, phrases like 'my ticker is acting up'
    should be routed toward a medical expert, not a coding expert.
    """).strip(),
    textwrap.dedent("""
    Persona memory is stored separately from general knowledge so
    Delilah can adapt her tone and style without polluting factual
    memory. Persona entries describe how she should speak, how formal
    or informal to be, and how to respond when the user is stressed
    or having a rough day.
    """).strip(),
    textwrap.dedent("""
    The orchestrator is designed so that timeless knowledge is stored
    in Qdrant, while ephemeral data from tools like live weather,
    sports scores, or stock prices is used at answer time and then
    discarded instead of being embedded as permanent memory.
    """).strip(),

    # Future critic/curator and jury-of-oracles
    textwrap.dedent("""
    In future phases, Delilah will incorporate a critic and curator
    layer. Multiple expert models or external LLMs can propose answers,
    and a curator model will compare them, detect disagreements, and
    choose or synthesize a final answer before anything is written to
    long-term memory.
    """).strip(),
    textwrap.dedent("""
    The jury-of-oracles design aims to reduce hallucinations by
    comparing answers from different sources. Only when answers agree
    and pass basic sanity checks will the system consider distilling
    them into new, curated facts stored in Qdrant.
    """).strip(),

    # Latency and performance philosophy
    textwrap.dedent("""
    Delilah is optimized for low-latency, local-first responses.
    The main bottlenecks are model inference speed on the GPU,
    network latency between satellites and the server, and the cost
    of retrieving and re-ranking context from Qdrant. The system
    is tuned to keep answers short and focused by default.
    """).strip(),
    textwrap.dedent("""
    The long-term plan includes upgrading the GPU beyond the RTX 3060
    so that larger or more specialized models can run locally while
    still maintaining interactive latency for voice conversations.
    """).strip(),
]

def chunk_texts(texts, max_batch_size=4):
    """Yield smaller batches for ingestion."""
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
    print(f"[seed-more] Using Brain ingest endpoint: {INGEST_ENDPOINT}")
    all_inserted = 0

    for batch_num, batch in enumerate(chunk_texts(MORE_TEXTS), start=1):
        payload = {
            "texts": batch,
            "user_id": DEFAULT_USER_ID,
            "source": DEFAULT_SOURCE,
        }
        print(f"[seed-more] Sending batch {batch_num} with {len(batch)} text(s)...")
        try:
            resp = requests.post(INGEST_ENDPOINT, json=payload, timeout=60)
        except Exception as e:
            print(f"[seed-more] ERROR: request failed: {e}")
            break

        if resp.status_code != 200:
            print(f"[seed-more] ERROR: HTTP {resp.status_code}: {resp.text}")
            break

        try:
            data = resp.json()
        except json.JSONDecodeError:
            print(f"[seed-more] ERROR: could not decode JSON response: {resp.text}")
            break

        inserted = data.get("inserted", 0)
        all_inserted += inserted
        print(f"[seed-more] Batch {batch_num} OK: inserted={inserted}")

    print(f"[seed-more] Done. Total inserted across all batches: {all_inserted}")


if __name__ == "__main__":
    main()
