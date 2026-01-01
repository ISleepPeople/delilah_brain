# Future Ideas / Design Backlog (Non-Binding)

## Agentic Delilah (North Star)

Goal: Delilah becomes a fully functioning agentic AI for the home.

Agentic definition:
- Plan → Act (tool use) → Verify → Iterate
- All actions are policy-gated, audited, and reversible
- Default safety posture: read-only tools first; mutating tools require allowlists + confirmation
- Verification before completion (tests/health checks/smoke checks)
- Long-horizon tasks run via explicit task queues and bounded budgets (no free-running loops)


## Cloud Fallback (Concept)
- Trigger conditions: answer not in RAG
- Provider order: chatgtp, gemini, claude best implementation for least latency
- Cost / rate limits:
- Failure behavior:

## Jury of Oracles (Concept)
- Asynchronous fan-out to {ChatGPT, Gemini, Claude}
- Aggregation strategy: voting / confidence scoring / contradiction detection
- Output: curated summary + citations + timestamp
- Human-in-the-loop optional
- Automate as much as possible within explicit policy gates, budgets, and verification requirements


##Persona Exemplars
- a small, curated persona_exemplars Qdrant collection containing hand-curated style exemplars (“sarcasm done well,” “comforting response patterns,” “arrogant-but-playful tone”), gated by policy and never
  automatically grown from raw conversation logs (to prevent persona drift).

## RAG Write Policy and ingest and ideas
- Do not store time-volatile facts (weather, sports, prices, schedules)
- Store only stable knowledge or “how-to find stable knowledge”
- Attach validity window metadata to any stored claim
- MedRAG Textbooks
- Multimodal RAG Pipeline (Phase 6): Use Meta-Llama-3.1-8B-Instruct ('Brain'), local Google SigLIP ('Eyes'),  
  and Qdrant ('Memory') to enable Visual Question Answering (VQA) and searchable image memory.
- Local RAG Staleness Verification Workflow: schedule a check of existing facts in Qdrant (e.g., monthly). 
  2. Sample high-value facts from the local knowledge base. 3. Use the Gemini API as a 'verification oracle' to
  check the truthfulness of the sampled local facts against current real-time data. 4. Use a Local MoE LLM to 
  compare the local fact and the verified answer to detect contradiction. 5. Flag contradictory facts in a
  'Pending Review' list for manual human review.


##Mixture of Experts
 - Vicuna-13B: Conversational LLM for MoE?
 - Data Reasoning Expert?
 - History Expert (Llama 3.1 8B Fine-tune) - For History & Humanities (RAG Collection: history_knowledge)
 - Scientific Expert (e.g., SciPhi 7B) - For Advanced Physics, Chemistry, Engineering (RAG Collection:
   science_knowledge)
 - Coding Expert
 - CREATE QDRANT COLLECTIONS FOR MIXTURE OF EXPERTS IF THIS IS BEST PRACTICE SO THE ORCHESTRATOR CAN SEARCH 
   ONLY RELAVENT COLLECTIONS prevents "context contamination" and keeps the knowledge base clean and efficient.
   THIS WILL HOPEFULLY PREVENT OR SHORTEN LATENCY
 - 
## Freshness Handling
- When RAG is queried:
  - detect time-sensitive intent (“today”, “latest”, “score”, “forecast”)
  - bypass RAG and call live tools
  - or return “RAG has historical context; live query required”

## Automation Targets
- n8n workflow: fallback → jury → curator → write-to-RAG
- curator writes:
  - stable facts to Qdrant
  - provenance + time + trace_id to Postgres
- Local Embedding Model (e.g., E5-Mistral or BGE-Large) is the preferred, cost-free alternative for RAG vector
  creation to ensure 100% privacy and zero cloud dependency. Do I need this?
- MQTT?


## Postgre Hardening
- When Env/config pinning + validation (fail fast, no silent defaults)
 - Your log_config_startup() print is not showing up in Docker logs. This is not blocking Phase 4.4, because Phase 4.4 is about timeouts/guards, not startup logging. We can proceed safely and circle back later to why print() isn’t surfacing (usually buffering/worker stdout behavior or the call not being reached in the runtime path we think).
 - True hard timeouts for Ollama/vector store require deeper changes (HTTP client timeouts in the Ollama wrapper and/or Qdrant client), but guards are the correct safe first layer.


## Planned (Phase 6.x)
- True client-level timeouts (HTTP/Qdrant)
- LangGraph routing
- Mixture-of-Experts
- Critic / curator loops
- n8n workflow automation
- Persona memory endpoint
- User mood inference
- Mixture-of-Experts routing
- Jury-of-Oracles fallback
- Tool arbitration / confidence scoring
- Cloud fallback models


##Persona
 - pick and choose what gets remembered/embedded
 - pick different traits in different contexts,” we’ll implement:
   tags like context:debug, context:comfort, context:automation
   and have orchestrator choose which tags to retrieve based on detected intent/mood.
 - Do not give long answers for weather calls
 - Be conversational
 - Enable 'Follow-Up Mode' to allow continuous dialogue without repeating the wake word, using Context-Aware 
   logic or an automation timer.

Not everything becomes memory
- Delilah flags:
    - Uncertain facts
    - Conflicting info
    - Repeated questions
- Human (you) can:
    - Approve
    - Edit
    - Reject
    - Re-tag
This prevents memory rot.

- Likely tools (future):
   - LoRA
   - QLoRA
   - Axolotl
   - Unsloth

##Wake Word
 - Wake Word: Train a custom OpenWakeWord model for the phrase 'Hey There Delilah'. ideally wake to "hey there
   Delilah" and "hey Delila"
 - Make the custom wake word work with voice recognition

##API and stack list
- OpenWeatherMap (Free tier, 1000 calls/day, replaces AccuWeather)
- FreshRSS (Local, open-source RSS aggregator, replaces paid news APIs)
- World Time API
- Places API
- Cloud Search API
- Google Docs API
- Google Sheets API
- Watchmode - fall back if tv show or movie not available via plex. Try to set up for movie or show to auto
  playback from whatever service has the show. deep-link URL. Requires explicit user confirmation before playback by default; optional “auto-play” preference must be explicit, revocable, and policy-governed (with full trace_id + tool-call audit).
- Music Streaming Workflow (MA): Unified, local-first music (Local files, Plex, YouTube Music, etc.).
  Authentication via browser method for tokens.
- Surya OCR - document ingest?
- Google Drive
- Gmail
- Calendar
- Google Maps API (Maps JavaScript API and Routes API) for Kiosk display: 1. Server-side Python function calls
  Routes API to calculate a route and gets the polyline. 2. Python function pushes the polyline to a Home
  Assistant entity state. 3. Kiosk-side custom HTML/JavaScript file reads the HA entity. 4. JavaScript uses the
  Maps JavaScript API to display the map, traffic, and route polyline in a Home Assistant Webpage (iFrame)
  card. I do not know if this is best implementation to get map on kiosk.
- Routes API (Replaces Directions and Distance Matrix) 
- Places API (Context Layer) - For real-time, location-based intelligence (business hours, reviews, category
  search). 
- TheSportsDB vs mysportsfeeds
- Enable the 'Vertex AI API' from the API Library. What does this do? Do I need it?
- SHOULD MEDIA FALLBACK IE WATCHMODE AND THE YOUTUBE MUSIC FALLBACK BE THROUGH HOME ASSISTANT?
- Travel, flights and hotels api or send a filtered anonymous search query with no user info


##Housekeeping
 - If you want Ruff to ignore the snapshot files permanently, add a .ruffignore or configure
   exclude in pyproject.toml later. For now, just target the two files.
 - Connect brain_v2 to the same Docker network as the shared Postgres container, and
   stop using host.docker.internal for intra-Docker traffic.
 - Get gluetun to work with pia and stay connected. Switzerland back ports.
 - .gitignore hygiene
 - vLLM as a future upgrade path for more performance, (both share an OpenAI-compatible API, making the switch
   easy). I don't know about this.

##Ideas, possibities don't know if I need or want
 - nextcloud
 - Personal Weather Station (PWS) Integration (e.g., Ambient Weather) for hyper-local weather data.
 - System Monitoring (e.g., Prometheus/Grafana)
 - Catastophic failure - If main server fails, RPi5 HA automates deployment of essential services (MQTT, 
   Minimal LLM (CPU), Limited Frigate (Coral USB), Minimal Qdrant) using a pre-loaded Docker Compose file to
   maintain basic smart home and voice control.
 -  Implement resource limits (CPU/RAM) on all Docker Compose services to prevent denial-of-service
 - Local RAG Staleness Verification Workflow: schedule a check of existing facts in Qdrant (e.g., monthly). 2. Sample high-value facts from the local knowledge base. 3. Use the Gemini API as a 'verification oracle' to check the truthfulness of the sampled local facts against current real-time data. 4. Use a Local MoE LLM to compare the local fact and the verified answer to detect contradiction. 5. Flag contradictory facts in a 'Pending Review' list for manual human review.
 - CAD Generation: External API (Zoo.dev) -> Code Generation Tool fusion360 readable
 - for home automation somehow have Delilah remember if we turned a light on (or something else) so you could ask her what lights are on, or can you do this in home assistant

##Asynchronous Execution
- The Core Strategy: Decoupling Tasks
    - Asynchronous (or "Async") execution allows your system to start one long-running task and
      immediately move on to the next task without waiting for the first one to finish.

      - RAG Retrieval (The Memory Lookup): When you ask a question ("What was the LVM
        command I used?"), the system first has to search the Vector Database. This search is an
        I/O-bound task (it waits for the disk or network). Async allows your system to start the search
        and immediately begin other tasks, like setting up the LLM inference call.
    - LLM Inference (The Thinking): The GPU is busy for hundreds of milliseconds generating the
      response. Async allows the server to keep its \text{CPU} active, monitoring for the next user
      input or preparing to stream the result to the \text{TTS} system.
- Streaming Response Generation
    - Asynchronous Streaming: The LLM generates the response token by token. Asynchronously,
      your system immediately passes each generated token/sentence to the \text{TTS} engine,
      which begins speaking almost instantly. This significantly reduces the Time-to-First-Token
      (TTFT) and makes the system feel much more natural and human-like.
How We Will Implement Asynchronicity - Preliminary not confirmed
    - Async Framework: We will use a Python asynchronous framework, such as asyncio or
      FastAPI, to build the central API that controls the flow.
    - Async Components: We must ensure all components in the chain support asynchronous calls
      (.acall() or .ainvoke() in many libraries):
    - Vector Database: We will use an async-compatible vector database (like Qdrant or an async
      connector for ChromaDB).
    - LLM Service: We will use an LLM inference engine (like \text{vLLM} or \text{Ollama}) that
      exposes an async/streaming API.
    - Pipelining: The \text{ASR} (Whisper), \text{RAG} lookup, \text{LLM} generation, and
      \text{TTS} are all connected via non-blocking, asynchronous queues to prevent any one step
      from blocking the others.
##kiosk
 - for synchronized, high-quality audio streaming is Snapcast paired with
Logitech Media Server (LMS). Can I use this in addision to OVOS and ovos/hivemind just kicks in when the wakeword is said? Is that the way to do it?

* LMS/Snapcast: This client-server architecture ensures perfect audio synchronization between
all your network speakers, which is critical for multi-room audio and avoiding the echoing often
seen when using basic \text{Wi-Fi} streaming.
run the Squeezelite
client on your Raspberry Pi voice satellites.