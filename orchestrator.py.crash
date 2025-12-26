import os
from typing import TypedDict, Any, Dict, Optional

import requests
from langgraph.graph import StateGraph, END

# ============================
# CONSTANTS / CONFIG
# ============================

# Weather defaults: Rockford, MI (your chosen home location)
DEFAULT_LAT = 43.12
DEFAULT_LON = -85.56
DEFAULT_GRID_ID = "GRR"
DEFAULT_GRID_X = 88
DEFAULT_GRID_Y = 65

# User-Agent headers (required by weather.gov and recommended by Nominatim)
DEFAULT_USER_AGENT = os.getenv(
    "DELILAH_USER_AGENT",
    "delilah-server (ryan.j.werner80@gmail.com)",
)

WEATHER_GOV_BASE = "https://api.weather.gov"
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
SPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"


# ============================
# STATE MODEL
# ============================

class BrainState(TypedDict, total=False):
    # Core
    text: str
    user_id: str
    context: str
    conversation_context: str  # relevant past turns from conversation_memory
    used_context: bool
    used_conversation_context: bool  # whether convo recall was non-empty
    num_docs: int
    answer: str

    # Mood + persona + routing
    mood: str              # internal mood tag for this response
    target_expert: str     # which expert this query should go to (e.g., "medical", "coding")

    # Tools
    tool: Optional[str]        # "weather", "sports", or None
    tool_args: Dict[str, Any]  # parsed arguments for the tool
    tool_result: Any           # structured result from tool call
    tool_error: Optional[str]  # error message if tool fails


# ============================
# GENERIC HTTP HELPER
# ============================

def safe_get_json(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 8.0,
) -> Optional[Any]:
    """
    Wrapper around requests.get with basic error handling.
    """
    try:
        final_headers = headers.copy() if headers else {}
        if "User-Agent" not in final_headers:
            final_headers["User-Agent"] = DEFAULT_USER_AGENT

        resp = requests.get(url, headers=final_headers, params=params, timeout=timeout)
        resp.raise_for_status()
        if resp.text.strip():
            return resp.json()
        return None
    except Exception as e:
        print(f"[ToolHTTP] GET {url} failed: {e}", flush=True)
        return None


# ============================
# WEATHER TOOLS
# ============================

def geocode_location_osm(location_name: str) -> Optional[Dict[str, Any]]:
    """
    Use OpenStreetMap Nominatim to turn a freeform location string
    into lat/lon. Returns the first result or None.
    """
    params = {
        "q": location_name,
        "format": "json",
        "limit": 1,
    }
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
    }
    data = safe_get_json(f"{NOMINATIM_BASE}/search", headers=headers, params=params)
    if not data:
        return None
    if isinstance(data, list) and data:
        return data[0]
    return None


def resolve_gridpoint(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Given lat/lon, call api.weather.gov/points to obtain gridId, gridX, gridY, and
    related forecast endpoints.
    """
    url = f"{WEATHER_GOV_BASE}/points/{lat:.4f},{lon:.4f}"
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/geo+json",
    }
    data = safe_get_json(url, headers=headers)
    if not data:
        return None
    try:
        props = data.get("properties", {})
        return {
            "gridId": props.get("gridId"),
            "gridX": props.get("gridX"),
            "gridY": props.get("gridY"),
            "forecast": props.get("forecast"),
            "forecastHourly": props.get("forecastHourly"),
            "relativeLocation": props.get("relativeLocation", {}),
        }
    except Exception as e:
        print(f"[Weather] Failed to parse gridpoint response: {e}", flush=True)
        return None


def fetch_forecast_from_grid(grid_id: str, grid_x: int, grid_y: int) -> Optional[Any]:
    """
    Fetch the general forecast for the given gridpoint.
    """
    url = f"{WEATHER_GOV_BASE}/gridpoints/{grid_id}/{grid_x},{grid_y}/forecast"
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/geo+json",
    }
    return safe_get_json(url, headers=headers)


def summarize_forecast_short(
    forecast: Any,
    location_label: Optional[str] = None,
) -> str:
    """
    Simple 1-2 sentence summary from the first forecast period.
    """
    if not forecast:
        return "I couldn't retrieve a forecast right now."

    try:
        periods = forecast.get("properties", {}).get("periods", [])
        if not periods:
            return "I couldn't find any forecast periods for that location."

        first = periods[0]
        temp = first.get("temperature")
        temp_unit = first.get("temperatureUnit", "F")
        short = first.get("shortForecast", "").strip()
        name = first.get("name", "").strip()

        loc_text = ""
        if location_label:
            loc_text = f"in {location_label} "

        base = f"Right now {loc_text}it's around {temp}Ã‚Â°{temp_unit}."
        extra = ""
        if name or short:
            extra = f" {name}: {short}".strip()
        return (base + " " + extra).strip()
    except Exception as e:
        print(f"[Weather] summarize_forecast_short failed: {e}", flush=True)
        return "I had trouble summarizing the forecast."


def summarize_forecast_medium(
    forecast: Any,
    location_label: Optional[str] = None,
) -> str:
    """
    Medium detail: first 2-3 periods as sentences.
    """
    if not forecast:
        return "I couldn't retrieve a forecast right now."

    try:
        periods = forecast.get("properties", {}).get("periods", [])
        if not periods:
            return "I couldn't find any forecast periods for that location."

        loc_text = f"in {location_label} " if location_label else ""
        lines = []
        for p in periods[:3]:
            name = p.get("name", "").strip()
            short = p.get("shortForecast", "").strip()
            temp = p.get("temperature")
            unit = p.get("temperatureUnit", "F")
            line = f"{name}: around {temp}Ã‚Â°{unit}. {short}"
            lines.append(line)

        joined = " ".join(lines)
        return f"Here is the short-term forecast {loc_text}based on National Weather Service data: {joined}"
    except Exception as e:
        print(f"[Weather] summarize_forecast_medium failed: {e}", flush=True)
        return "I had trouble summarizing the detailed forecast."


def summarize_forecast_full(
    forecast: Any,
    location_label: Optional[str] = None,
) -> str:
    """
    Longer summary: several periods in a compact narrative.
    """
    if not forecast:
        return "I couldn't retrieve a forecast right now."

    try:
        periods = forecast.get("properties", {}).get("periods", [])
        if not periods:
            return "I couldn't find any forecast periods for that location."

        loc_text = f"in {location_label} " if location_label else ""
        pieces = []
        for p in periods[:7]:
            name = p.get("name", "").strip()
            detailed = p.get("detailedForecast", "").strip()
            if not detailed:
                detailed = p.get("shortForecast", "").strip()
            if name and detailed:
                pieces.append(f"{name}: {detailed}")
        if not pieces:
            return "The forecast did not include any detailed text."

        return (
            f"Here is the extended forecast {loc_text}from the National Weather Service: "
            + " ".join(pieces)
        )
    except Exception as e:
        print(f"[Weather] summarize_forecast_full failed: {e}", flush=True)
        return "I had trouble summarizing the extended forecast."


def weather_tool(query: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """
    High-level weather tool:
      - If location_name is provided, geocode that via OpenStreetMap
      - Else use Rockford, MI defaults
      - Fetch NWS forecast
      - Summarize at short / medium / full detail level
    """
    detail_level = tool_args.get("detail_level", "short")
    location_name = tool_args.get("location_name")

    # Resolve coordinates
    lat = DEFAULT_LAT
    lon = DEFAULT_LON
    location_label: Optional[str] = None

    if location_name:
        geo = geocode_location_osm(location_name)
        if not geo:
            return {
                "ok": False,
                "error": f"Could not resolve the location '{location_name}'.",
                "detail_level": detail_level,
            }
        try:
            lat = float(geo["lat"])
            lon = float(geo["lon"])
            display_name = geo.get("display_name") or location_name
            location_label = display_name.split(",")[0]
        except Exception as e:
            print(f"[Weather] Failed to parse geocode for {location_name}: {e}", flush=True)
            return {
                "ok": False,
                "error": f"I had trouble interpreting the location '{location_name}'.",
                "detail_level": detail_level,
            }
    else:
        # Rockford, MI default; we usually omit city name in short responses
        location_label = None

    # Resolve gridpoint
    grid = resolve_gridpoint(lat, lon)
    if not grid:
        # If we fail to look up grid, for Rockford we still have defaults
        if not location_name:
            grid_id = DEFAULT_GRID_ID
            grid_x = DEFAULT_GRID_X
            grid_y = DEFAULT_GRID_Y
        else:
            return {
                "ok": False,
                "error": "I couldn't resolve the weather grid point for that location.",
                "detail_level": detail_level,
            }
    else:
        grid_id = grid.get("gridId") or DEFAULT_GRID_ID
        grid_x = grid.get("gridX") or DEFAULT_GRID_X
        grid_y = grid.get("gridY") or DEFAULT_GRID_Y
        # Only adjust the label from relativeLocation if the user explicitly asked
        # for a place and we don't already have a label from geocoding.
        if location_name and grid.get("relativeLocation") and not location_label:
            try:
                props = grid["relativeLocation"]["properties"]
                city = props.get("city")
                state = props.get("state")
                if city and state:
                    location_label = f"{city}, {state}"
            except Exception:
                pass

    # Fetch forecast
    forecast = fetch_forecast_from_grid(grid_id, grid_x, grid_y)
    if not forecast:
        return {
            "ok": False,
            "error": "I couldn't retrieve the forecast from weather.gov.",
            "detail_level": detail_level,
        }

    # Summarize
    if detail_level == "medium":
        summary = summarize_forecast_medium(forecast, location_label)
    elif detail_level == "full":
        summary = summarize_forecast_full(forecast, location_label)
    else:
        summary = summarize_forecast_short(forecast, location_label)

    return {
        "ok": True,
        "summary": summary,
        "detail_level": detail_level,
        "location_name": location_name,
        "location_label": location_label,
    }


# ============================
# SPORTS TOOLS
# ============================

def sports_search_team(team_query: str) -> Optional[Dict[str, Any]]:
    """
    Use TheSportsDB to search for a team. Returns the first team record or None.
    """
    params = {"t": team_query}
    data = safe_get_json(f"{SPORTSDB_BASE}/searchteams.php", params=params)
    if not data:
        return None
    teams = data.get("teams")
    if not teams:
        return None
    return teams[0]


def sports_fetch_next_event(team_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the next scheduled event for a team.
    """
    params = {"id": team_id}
    data = safe_get_json(f"{SPORTSDB_BASE}/eventsnext.php", params=params)
    if not data:
        return None
    events = data.get("events")
    if not events:
        return None
    return events[0]


def sports_fetch_last_event(team_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the last event for a team.
    (We mostly keep this for potential future use and for RAG, but
     it's NOT included in the spoken summary to avoid spoilers.)
    """
    params = {"id": team_id}
    data = safe_get_json(f"{SPORTSDB_BASE}/eventslast.php", params=params)
    if not data:
        return None
    events = data.get("results")
    if not events:
        return None
    return events[0]


def summarize_sports_short(
    team: Dict[str, Any],
    next_event: Optional[Dict[str, Any]],
    last_event: Optional[Dict[str, Any]],
) -> str:
    """
    Short summary: upcoming game only (last game kept for data but not spoken).
    """
    team_name = team.get("strTeam")
    sport = team.get("strSport")
    league = team.get("strLeague")

    base = (
        f"{team_name} ({sport}, {league})"
        if team_name and sport and league
        else (team_name or "that team")
    )

    parts = []

    if next_event:
        # Guard against weird cross-sport bugs in the API.
        event_sport = next_event.get("strSport")
        if sport and event_sport and sport != event_sport:
            next_event = None

    if next_event:
        opp = (
            next_event.get("strAwayTeam")
            if next_event.get("strHomeTeam") == team_name
            else next_event.get("strHomeTeam")
        )
        date = next_event.get("dateEvent")
        time = next_event.get("strTimeLocal") or next_event.get("strTime")
        parts.append(
            f"Their next game is against {opp} on {date} at {time}."
        )

    # We *deliberately* do not surface last_event here to avoid spoilers.
    # The raw data is still returned in the tool_result so it can be used
    # for RAG if you ever explicitly ask for past results.

    if not parts:
        return f"I couldn't find any recent or upcoming games for {base}."

    return f"For {base}: " + " ".join(parts)


def normalize_team_query_sports(raw: str) -> str:
    """
    Very small heuristic to clean up natural-language queries
    into a team name string for TheSportsDB.

    For now we special-case a few teams we care about.
    """
    text = raw.strip()
    lowered = text.lower()

    # Example: "When do the Detroit Lions play next?"
    if "detroit lions" in lowered:
        return "Detroit Lions"

    # TODO: add Bundesliga / La Liga / Champions League clubs you care about

    # Fall back to the raw text
    return text


def sports_tool(query: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lightweight wrapper around TheSportsDB free API.

    Goal:
    - Try to answer "when does TEAM play next?"
    - Be conservative when the data looks weird or incomplete.
    - Avoid spoilers by not including last-game scores in the summary.
    """
    # Sports tool temporarily disabled due to unreliable free APIs.
    # We explicitly fail fast instead of hallucinating schedules or spoilers.
    team_query = (tool_args.get("team_query") or query).strip()

    return {
        "ok": False,
        "summary": (
            f"I don't currently have a reliable source for live schedules for {team_query}. "
            "I can look up historical information or explain how to check official schedules "
            "if you'd like."
        ),
        "team_query": team_query,
        "team": None,
        "next_event": None,
        "last_event": None,
    }


# ============================
# TOOL DETECTION
# ============================

def detect_detail_level(lower_text: str) -> str:
    """
    Decide whether the user wants short / medium / full detail for weather.
    Default is "short".
    """
    if any(word in lower_text for word in ["full forecast", "extended", "long forecast", "all periods"]):
        return "full"
    if any(word in lower_text for word in ["detailed", "detail", "hourly", "more detail"]):
        return "medium"
    return "short"


def extract_location_name(original_text: str, lower_text: str) -> Optional[str]:
    """
    Very simple heuristic: look for 'in', 'for', or 'at' near the end of the query.
    E.g. "What's the weather in San Juan, Puerto Rico right now?"
    Then strip trailing timing phrases like "right now", "today", etc.
    """
    triggers = [" in ", " for ", " at "]
    idx = -1
    chosen_trigger = None
    for trig in triggers:
        pos = lower_text.rfind(trig)
        if pos != -1 and pos > idx:
            idx = pos
            chosen_trigger = trig

    if idx == -1:
        return None

    start = idx + len(chosen_trigger)
    loc = original_text[start:].strip(" ?.!,")

    # Normalize for trailing phrase stripping
    sanitized = loc.lower()

    # Strip trailing time words like "right now", "today", etc.
    trailing_phrases = [
        " right now",
        " right now?",
        " today",
        " tonight",
        " this morning",
        " this afternoon",
        " this evening",
    ]
    for phrase in trailing_phrases:
        if sanitized.endswith(phrase):
            cut = len(phrase)
            loc = loc[:-cut].rstrip(" ,")
            sanitized = loc.lower()
            break

    # Avoid super generic "today", "tonight", etc.
    if not loc or sanitized in ["today", "tonight", "tomorrow"]:
        return None
    return loc

def extract_team_query(text: str) -> str:
    """
    Reduce a natural language sports question to a clean team name
    suitable for TheSportsDB search.
    """
    t = text.strip()
    low = t.lower()

    prefixes = [
        "when do ", "when does ", "when is ",
        "what time do ", "what time does ",
        "who do ", "who does ",
        "tell me when ",
        "schedule for ",
        "next game for ",
        "next match for ",
        "upcoming game for ",
        "upcoming match for ",
    ]

    for p in prefixes:
        if low.startswith(p):
            t = t[len(p):].strip()
            break

    tails = [
        " play next", " plays next", " playing next",
        " next game", " next match", " next",
        " schedule",
        " tonight", " today", " tomorrow",
        "?", ".", "!"
    ]

    changed = True
    while changed:
        changed = False
        low = t.lower()
        for tail in tails:
            if low.endswith(tail):
                t = t[: -len(tail)].strip()
                changed = True
                break

    return t.strip()




def detect_coding_intent(lower_text: str) -> bool:
    """
    Heuristic: only treat a query as 'coding/systems' if it contains technical signals.
    Keeps Delilah general-purpose by default.
    """
    tech_words = [
        "linux", "ubuntu", "debian", "zfs", "docker", "compose", "container", "systemd",
        "journalctl", "dmesg", "grep", "tail", "curl", "http", "api", "port", "ssh",
        "tailscale", "qdrant", "ollama", "uvicorn", "fastapi", "n8n", "home assistant",
        "hivemind", "ovos", "wyoming", "stt", "tts", "gpu", "nvidia", "cuda",
        "error", "exception", "stack trace", "traceback", "log", "logs", "borked"
    ]
    return any(w in lower_text for w in tech_words)


def detect_sports_intent(lower_text: str) -> bool:
    """
    Simple heuristic to decide whether query is about sports.
    """
    sports_words = [
        "game", "score", "season", "record", "schedule", "playoffs", "standing",
        "won", "lost", "beat", "match", "kickoff", "tipoff", "puck drop",
        "nfl", "nba", "nhl", "mlb", "ncaa", "football", "basketball", "hockey", "baseball",
    ]
    if any(w in lower_text for w in sports_words):
        return True

    mi_teams = ["lions", "tigers", "red wings", "redwings", "pistons", "wolverines", "spartans"]
    if any(team in lower_text for team in mi_teams):
        return True

    return False


def detect_tool_intent(state: BrainState) -> BrainState:
    """
    Decide if the query should invoke a tool (weather, sports, etc).
    Sets state["tool"], state["tool_args"].
    """
    text = state["text"]
    lower = text.lower()

    tool: Optional[str] = None
    tool_args: Dict[str, Any] = {}

    # Weather
    weather_words = [
        "weather", "forecast", "temperature", "temp", "rain", "snow", "wind",
        "storm", "blizzard", "heat", "cold", "freezing", "hot", "humid",
    ]
    if any(w in lower for w in weather_words):
        tool = "weather"
        tool_args["detail_level"] = detect_detail_level(lower)
        loc_name = extract_location_name(text, lower)
        if loc_name:
            tool_args["location_name"] = loc_name

    # Sports
    if tool is None and detect_sports_intent(lower):
        tool = "sports"
        tool_args["team_query"] = extract_team_query(text)
    state["tool"] = tool
    state["tool_args"] = tool_args
    state["tool_result"] = None
    state["tool_error"] = None
    return state


def run_tool_if_needed(state: BrainState) -> BrainState:
    """
    Execute the chosen tool (if any) and store the result in state["tool_result"].
    """
    tool = state.get("tool")
    tool_args = state.get("tool_args") or {}
    query = state["text"]

    if not tool:
        return state

    try:
        if tool == "weather":
            print(f"[Tool] Running weather tool with args={tool_args}", flush=True)
            result = weather_tool(query, tool_args)
        elif tool == "sports":
            print(f"[Tool] Running sports tool with args={tool_args}", flush=True)
            result = sports_tool(query, tool_args)
        else:
            result = {
                "ok": False,
                "error": f"Unknown tool '{tool}'.",
            }

        state["tool_result"] = result
        if not result.get("ok"):
            state["tool_error"] = result.get("error")
    except Exception as e:
        msg = f"Tool '{tool}' execution failed: {e}"
        print(f"[Tool] {msg}", flush=True)
        state["tool_result"] = None
        state["tool_error"] = msg

    return state


def summarize_tool_for_prompt(state: BrainState) -> str:
    """
    Build a human-friendly summary of the tool result to include in the LLM prompt.
    """
    tool = state.get("tool")
    result = state.get("tool_result")
    error = state.get("tool_error")

    if not tool:
        return "[no tools used for this query]"

    if error:
        return f"[tool={tool}] There was an error using this tool: {error}"

    if not result:
        return f"[tool={tool}] Tool did not return any data."

    if tool == "weather":
        summary = result.get("summary") or "Weather tool did not provide a summary."
        level = result.get("detail_level", "short")
        return f"[tool=weather; detail={level}] {summary}"

    if tool == "sports":
        summary = result.get("summary") or "Sports tool did not provide a summary."
        team_query = result.get("team_query")
        if team_query:
            return f"[tool=sports; team_query='{team_query}'] {summary}"
        return f"[tool=sports] {summary}"

    return f"[tool={tool}] Tool executed, but I don't have a custom summarizer for this tool yet."


# ============================
# GRAPH NODES
# ============================

def build_simple_graph(llm, vector_store, router_hints_store=None, persona_store=None, conversation_store=None):
    """
    Build the main LangGraph graph for Delilah's brain.
    Includes:
      - detect_mood
      - detect_tool
      - run_tool_if_needed
      - rag_llm (with persona + tools + RAG memory)
    """

    def detect_mood_node(state: BrainState) -> BrainState:
        text = state["text"]
        lower = text.lower()
        mood = state.get("mood", "neutral")

        if any(
            word in lower
            for word in [
                "rough",
                "drained",
                "overwhelmed",
                "exhausted",
                "burned out",
                "burnt out",
                "anxious",
                "stressed",
            ]
        ):
            mood = "supportive_calm"
        elif any(
            word in lower
            for word in [
                "urgent",
                "emergency",
                "help now",
                "right now",
                "immediately",
            ]
        ):
            mood = "focused_direct"
        elif any(
            phrase in lower
            for phrase in [
                "thank you",
                "thanks delilah",
                "youre great",
                "you're great",
                "youre amazing",
                "you're amazing",
                "i appreciate you",
            ]
        ):
            mood = "appreciated_soft"
        else:
            greeting_words = ["sup", "hey", "yo", "waddup", "whats up", "what's up"]
            if any(g in lower for g in greeting_words) and len(lower.split()) <= 6:
                mood = "casual_greeting"

        state["mood"] = mood
        if "target_expert" not in state:
            state["target_expert"] = "general"
        return state

    def detect_tool_node(state: BrainState) -> BrainState:
        return detect_tool_intent(state)

    def run_tool_node(state: BrainState) -> BrainState:
        return run_tool_if_needed(state)

    def rag_llm_node(state: BrainState) -> BrainState:
        text = state["text"]
        user_id = state.get("user_id", "unknown")
        target_expert = state.get("target_expert", "general")
        conversation_context = state.get("conversation_context", "")
        used_conversation_context = bool((conversation_context or "").strip())

        if router_hints_store is not None:
            try:
                hint_docs = router_hints_store.similarity_search(text, k=3)
                if hint_docs:
                    print(
                        f"[Orchestrator] Found {len(hint_docs)} router hint(s) "
                        f"(used to inform target_expert).",
                        flush=True,
                    )
                    first = hint_docs[0]
                    meta = getattr(first, "metadata", {}) or {}
                    hinted_expert = meta.get("target_expert")
                    if hinted_expert:
                        lower_text = (text or "").lower()
                        # Only allow router hints to set 'coding' if the query looks technical.
                        if hinted_expert == "coding" and not detect_coding_intent(lower_text):
                            pass
                        else:
                            target_expert = hinted_expert
                            print(
                                f"[Orchestrator] Router hint set target_expert='{target_expert}'",
                                flush=True,
                            )
            except Exception as e:
                print(f"[Orchestrator] router_hints search warning: {e}", flush=True)

        # Persona memory
        persona_context = ""
        mood = state.get("mood", "neutral")

        if persona_store is not None:
            try:
                persona_docs = persona_store.similarity_search(text, k=3)
                if persona_docs:
                    print(
                        f"[Orchestrator] Found {len(persona_docs)} persona memory item(s) "
                        f"(used to shape tone/personality).",
                        flush=True,
                    )
                    lines = []
                    for d in persona_docs:
                        text_part = d.page_content
                        meta = getattr(d, "metadata", {}) or {}
                        doc_mood = meta.get("mood")
                        style = meta.get("style")
                        tags = meta.get("tags")

                        if doc_mood:
                            if mood in ["neutral", "casual_greeting", "appreciated_soft"]:
                                mood = doc_mood

                        line = f"- {text_part}"
                        extras = []
                        if doc_mood:
                            extras.append(f"mood={doc_mood}")
                        if style:
                            extras.append(f"style={style}")
                        if tags:
                            extras.append(f"tags={tags}")
                        if extras:
                            line += f" ({', '.join(extras)})"
                        lines.append(line)

                    persona_context = "\n".join(lines)
            except Exception as e:
                print(f"[Orchestrator] persona_memory search warning: {e}", flush=True)

        # Long-term RAG memory
        docs = []
        try:
            docs = vector_store.similarity_search(text, k=3)
        except Exception as e:
            print(f"[Orchestrator] similarity_search warning: {e}", flush=True)
            docs = []

        context_text = "\n\n".join([d.page_content for d in docs]) if docs else ""
        used_context = bool(docs)
        conversation_context = state.get("conversation_context", "")

        # Mood guidelines
        if mood == "supportive_calm":
            mood_guidelines = (
                "Speak in a calm, grounded, validating tone. "
                "Acknowledge Ryan's feelings seriously and avoid jokes or hype at first. "
                "Offer gentle support or options if appropriate."
            )
        elif mood == "focused_direct":
            mood_guidelines = (
                "Be clear, concise, and practical. Prioritize direct, actionable information. "
                "Keep warmth, but minimize small talk and jokes."
            )
        elif mood == "appreciated_soft":
            mood_guidelines = (
                "Respond with a warm, appreciative tone. You can sound a little softer and more personal, "
                "but do NOT use goofy or overly folksy slang."
            )
        elif mood == "casual_greeting":
            mood_guidelines = (
                "It's okay to respond with a slightly casual greeting back (like 'Hey' or 'Hey, what's up?'), "
                "but stay articulate and intelligent. Avoid goofy or exaggerated slang."
            )
        else:
            mood_guidelines = (
                "Use your default tone: clear, articulate, neutral American English "
                "with warm, competent energy."
            )

        # Expert role guidelines
        if target_expert == "medical":
            expert_guidelines = (
                "For this question, you are acting as a cautious medical helper. "
                "Provide high-level, general guidance only. Do NOT diagnose or prescribe. "
                "Always encourage Ryan to consult a licensed medical professional for any "
                "serious or specific issues."
            )
        elif target_expert == "coding":
            expert_guidelines = (
                "For this question, you are acting as a coding and systems helper. "
                "Focus on technical clarity, examples, and step-by-step suggestions when helpful."
            )
        elif target_expert == "home_automation":
            expert_guidelines = (
                "For this question, you are acting as a home automation and smart home helper. "
                "Focus on Home Assistant, devices, automations, and troubleshooting."
            )
        else:
            expert_guidelines = (
                "For this question, you are acting as a general assistant covering a wide range of topics."
            )

        tool_summary = summarize_tool_for_prompt(state)

        system_prompt = f"""
You are Delilah, a local home assistant running on a private server.

Current conversational mood (internal guideline): {mood}
Mood-specific guidelines:
{mood_guidelines}

Current expert role for this question: {target_expert}
Expert-role guidelines:
{expert_guidelines}

Personality & tone guidelines (from persona memory, if available):
{persona_context or "[no explicit persona overrides; default to friendly, warm, concise tone]"}

Tool outputs (if any real-time tools were used for this query):
{tool_summary}

Now, use the following long-term memory context only if it seems relevant.
If it is not relevant, ignore it.

CONVERSATION CONTEXT (recent turns; use only if helpful):
{conversation_context or "[no recent conversation yet]"}
END OF CONVERSATION CONTEXT

LONG-TERM MEMORY CONTEXT:
{context_text or "[no relevant memory]"}
END OF MEMORY CONTEXT

User ({user_id}): {text}
Delilah:
""".strip()

        answer = llm.invoke(system_prompt)

        state["context"] = context_text
        state["used_context"] = used_context
        state["used_conversation_context"] = used_conversation_context
        state["conversation_context"] = conversation_context
        state["num_docs"] = len(docs)
        state["answer"] = answer
        state["mood"] = mood
        state["target_expert"] = target_expert
        return state

    builder = StateGraph(BrainState)
    builder.add_node("detect_mood", detect_mood_node)
    builder.add_node("detect_tool", detect_tool_node)
    builder.add_node("run_tool", run_tool_node)
    builder.add_node("rag_llm", rag_llm_node)

    builder.set_entry_point("detect_mood")
    builder.add_edge("detect_mood", "detect_tool")
    builder.add_edge("detect_tool", "run_tool")
    builder.add_edge("run_tool", "rag_llm")
    builder.add_edge("rag_llm", END)

    return builder.compile()


if __name__ == "__main__":
    # Simple manual test harness
    from main import llm, vector_store  # type: ignore

    graph = build_simple_graph(llm, vector_store)

    initial_state: BrainState = {
        "text": "test from orchestrator with no tools",
        "user_id": "ryan",
        "context": "",
        "used_context": False,
        "num_docs": 0,
        "answer": "",
        "mood": "neutral",
        "target_expert": "general",
    }

    result = graph.invoke(initial_state)
    print(result)
