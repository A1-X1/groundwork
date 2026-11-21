# How Groundwork uses Mistral

Mistral powers every natural-language part of Groundwork: two agents that build new use cases, a command parser for the map, and Voxtral for listening and speaking. Scores themselves are never produced by an LLM: they come from the transparent weighted formula and the trained feasibility model.

## 1. Agents (`backend/agent/`)

| Agent | Model | Job |
|---|---|---|
| **Groundwork Planner** | `mistral-large-latest` | Turns "I want to build X" into a working use case. It picks existing data layers, adds missing ones from a vetted registry of free sources, builds them **only for your region**, writes the scoring profile, designs a 3D model, checks **Azure ML** and trains the feasibility model there, then verifies results and drives the map. |
| **Groundwork Data Aggregator** | `mistral-large-latest` | Runs when Azure ML isn't connected and the user picks it. It builds the same use case from aggregated data with no ML training, uses local value ranges (`layer_stats`) to set sensible weights, and writes a plain-language note for every weight ("higher crime per 1,000 residents gives a worse score; London median ≈ 67"). |

**Tools (function calling).** Both agents act only through validated Groundwork tools (`backend/agent/tools.py`): `get_catalog`, `search_data_sources`, `add_layer`, `build_layers`, `layer_stats`, `create_profile`, `design_3d_model`, `azure_status`, `train_model`, `preview_scores`, `ui_command` and `request_user_action`. Everything they create is **data, not code**: YAML layers from fixed templates, a validated profile, and a JSON 3D spec (≤ 5,000 triangles) that the frontend renders with three.js.

**Two ways to run them:**
1. **In the app** (`POST /agent/run`, streamed as server-sent events): `backend/agent/runner.py` uses Mistral chat completions with tool calling. `context.agent = "aggregator"` switches agent.
2. **As Mistral managed agents** (`backend/agent/managed/`, the `mistralai-agents` SDK, Python 3.12+). The Planner is the main `agents.Agent` and the Aggregator is its `agents.Subagent`; both reuse the same tools.
   ```bash
   cd backend/agent/managed
   export MISTRAL_API_KEY=...        # your key
   uv run agents chat                # talk to the Planner in the terminal
   uv run agents serve               # run locally + register in your workspace (needs workflows enabled on the key)
   uv run agents deploy              # Mistral hosts it (needs workflows enabled)
   uv run agents list                # see what's registered
   ```
   Served or deployed agents appear in **Mistral AI Studio → Agents** (console.mistral.ai), where you can chat with and debug them.

**Behaviour rules** (`instructions.md`, `aggregator.md`):
- check Azure before any training and ask the user ("Azure ML isn't connected: connect it, or use the Mistral data aggregator")
- never present synthetic data as real
- never guess place names; areas come from OpenStreetMap reverse geocoding
- split compound requests ("pan to London then find houses") into an ordered UI command queue
- skip commands when the map is already there ("You're already looking at Tokyo")
- keep spoken answers to 1–2 sentences with 1–2 recommended areas

## 2. Map command parser (`backend/api/assistant.py`)

`POST /assistant/command` sends the typed or spoken request to `mistral-small-latest`, which returns structured UI commands (`PAN_COUNTRY`, `PAN_CITY`, `SET_PROFILE`, `SET_OVERLAY`, `SHOW_TOP_SITES`, `PLACE_SITE`, …). Without a key it falls back to an offline rule-based parser.

## 3. Voxtral: voice in and out

- **Speech to text:** recorded audio from the voice orb goes to Mistral's transcription endpoint (`/v1/audio/transcriptions`, model `voxtral-mini-latest`), and the text is then handled as a command or agent prompt.
- **Text to speech:** replies are spoken with Voxtral TTS (`/v1/audio/speech`, model `voxtral-mini-tts-latest`). The default voice is "Paul" (`en_paul`), and each reply picks a tone variant from its wording (e.g. cheerful, confident). `GROUNDWORK_VOICE` switches speaker (`gb_oliver`, `gb_jane`).

## Keys and cost

One `MISTRAL_API_KEY` in `.env` enables everything above. The key stays on the server; the browser never sees it.
