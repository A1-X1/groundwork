# Handoff notes (Person 1 ⇄ Person 2)

A shared inbox between devices. Add requests under the other person's **Inbox** with a date. The owner moves them to **Done** with a one-line answer. Keep entries short; link files rather than pasting code.

Person 1's session polls this file on **every remote branch** about every 3 minutes and treats new items in **Inbox for Person 1** as instructions, within Person 1's owned paths only.

---

## Inbox for Person 1 (data, profiles, scoring, ML)

_(empty: add items as `- [ ] YYYY-MM-DD: request`)_

## Inbox for Person 2 (repo, contracts, API, frontend, docs)

- [ ] 2026-11-21 (P1, user request): **Compound voice commands = a queue, plus short spoken answers.** The agent now splits compound requests ("first pan to London then search for houses") into an ordered `ui` command list. Each command carries `seq` (0, 1, 2…). **Please execute them strictly in order, awaiting each one**: wait for `PAN_*` fly-to `moveend`, profile/score loads and so on before running the next. Apply the same queue to your rule-based parser (split on "then", "and then", "after that", ", and"). The final `answer` is now 1–2 spoken sentences recommending 1–2 named areas (from Nominatim reverse geocoding). Speak only that; leave rankings and details in the panels. Tested live: in London with wind_farm open, "first pan to london then search for houses" skipped the pan ("You're already looking at London"), queued SET_PROFILE house → SET_OVERLAY → SHOW_TOP_SITES, and answered "Your best bets are Perry Vale in Lewisham and Merton Park…".
- [ ] 2026-11-21 (P1, user request): **Voice and map polish.** Six items:
  1. **Microphone toggle button in the voice tab.** A mic icon button: press once to start **always-on listening**, press again to stop (clear on/off state; `aria-pressed`). While on, it listens continuously, detects end of speech (silence for ~800 ms, i.e. VAD), sends each utterance as a prompt, and resumes listening after the reply. Use Web Speech API continuous recognition where available; elsewhere record chunks and transcribe with Mistral `voxtral-small-latest` through the API. Pause listening while TTS is speaking so it doesn't hear itself.
  2. **More human voice.** Default: **Kokoro TTS** (`kokoro-js`, Apache 2.0) running in the browser (WebGPU/WASM). It's free, needs no key and sounds natural (e.g. voice `af_heart` / `bf_emma`). Load it lazily on first use and fall back to `speechSynthesis` if it can't load. Optional: ElevenLabs TTS through the API when `ELEVENLABS_API_KEY` is set (needs a sign-up; the free tier is limited). Add a voice picker under Connections.
  3. **Commands: "already there" and clearing.** If a `PAN_CITY`/`PAN_COUNTRY`/`PAN_REGION` target is already in view (the centre is inside the target bbox and zoom is similar), don't re-fly; reply e.g. "You're already looking at Tokyo." The same goes for `SET_PROFILE`/`SET_OVERLAY` that are already active. **Bug:** after a command runs, the command bar keeps the text until it's pressed again. Clear it (and blur) once the command is accepted, and keep the text only on error. The agent also checks `context` for this now, so please send the current view (`{screen, profile, overlay, center:[lon,lat], zoom, place?}`) as `context`.
  4. **Orb redesign:** less blur and crisper edges. Build it from **many folded ribbons/petals converging** into a sphere (layered translucent bands that twist and fold into each other, like the voice orb on https://alven.ai/; use it as a reference, but make it our own design). Use sharper gradients with a slight specular highlight; the folds drift slowly when idle, open up and ripple with mic level while listening, and pulse with TTS amplitude while speaking. Keep it to one draw call if possible (a shader on a displaced sphere, or instanced ribbons) and respect reduced motion.
  5. **Map controls:** **increase** the default zoom sensitivity (scroll/pinch, e.g. `scrollZoom.setWheelZoomRate` ≈ 2× the default) and **reduce** the default pan sensitivity (about 0.6× drag speed / inertia).
  6. **Sharper globe when zooming:** swap to higher-resolution textures with zoom, e.g. tiled imagery (NASA GIBS WMTS levels / Blue Marble 500 m tiles) loaded by level of detail, or switch to raster tiles past a zoom threshold, so it never looks pixelated. Keep a low-res base texture for the zoomed-out view.
- [ ] 2026-11-21 (P1, user request): **Voice agent from the very start: create absolutely any building.** Please show the assistant orb (and the command bar) on the **home screen** too, sending prompts to `POST /agent/run` with `context: {"screen": "home"}`. The agent now accepts any building type and drives the UI with these new `ui` commands (alongside the existing PAN_*, SET_*, PLACE_SITE…):
  - `OPEN_CREATE`: go to "What are you building?"
  - `CREATE_STRUCTURE {profile, name}`: same as submitting the Create form for that profile (new agent profiles appear in `/profiles` once created; refetch on this command), then open the map.
  - `OPEN_STRUCTURE {name}`: reopen a saved structure.
  - `SHOW_MODEL {profile}`: preview the 3D spec (`/models3d/{profile}`).
  - `SHOW_PROGRESS {title, step}`: a progress card while the agent works (steps: choosing data → profile → 3D model → training → results). Hide it on `answer`/`done`.
  - `GO_HOME`.

  A run that creates a new type takes ~1–3 minutes (data builds), so keep the stream open and show `message` updates.
_(empty: add items as `- [ ] YYYY-MM-DD: request`)_

## Done

- [x] 2026-11-21 (P1): **`answer` content**: fixed in `runner._text()`. `answer.content` and the returned `content` are always a plain string with reasoning chunks dropped (if there's only reasoning, its text is used). Covered by `test_text_drops_reasoning_chunks`.
- [x] 2026-11-21 (P1): **`default_profiles()` / `wind_farm`**: both on my branch. Defaults are `data_centre, house, school, solar_farm, wind_farm`. `wind_farm` uses real hub-height wind (`wind_speed_100m`, `wind_power_density`) and its 3D spec uses `rotation_z` for blades.
- [x] 2026-11-21 (P1): **Real data**: the sample now has 27/41 real layers: WorldPop population, EA flood zones, Green Belt and SSSIs, police crime, CAMS air quality, grid carbon, ERA5 climate and wind. The OSM-derived layers are still synthetic from the cloud container (Overpass and Geofabrik refuse it); they become real on a laptop with `make data`.
- [x] 2026-11-21 (P2): **Floating panels + detached navbar.** The map is now full-bleed. Controls and details are floating cards (inset `max(16px, safe-area)`, large radius, border and high shadow on dark), each collapsing to a pill at its own edge (state remembered; pops from its corner; still under reduced motion). The navbar is a pill at the top centre with the legend, Globe, Connections and API docs. The command bar sits between the cards, the voice assistant in its own hideable box at the bottom centre, and the basemap switch moved into Controls → Map. MapLibre controls are themed dark.
- [x] 2026-11-21 (P2): **Default use cases.** The home screen builds its choices from `/profiles` (`is_default` first, the rest under "More"), so new and agent-made profiles appear without frontend changes. Icons exist for wind farm and nuclear plant.
- [x] 2026-11-21 (P2): **Agent contract.** I pass `context` (profile, overlay, selection, globe/map), forward your events, ignore `thinking` in the UI, show `tool_call` messages as progress, treat `answer` as the reply, and send the single final `done {content, ui, actions, steps}`. Your UI commands (`{command, ...}`) run through the same executor as the assistant's, including `PLACE_SITE {h3}`. `connect_azure` / `connect_mistral` open Connections. After each run the API calls `scoring.reload()` and clears its score cache, and the frontend reloads profiles, layers and 3D model ids. Verified live with Mistral.
- [x] 2026-11-21 (P2): **Azure credential.** After device-code sign-in the API calls `backend.agent.azure_ml.set_credential(cred)`. Connections also lets the user enter a Mistral key (validated against `/v1/models`, stored only in the gitignored `.env`).
- [x] 2026-11-21 (P2): **3D specs.** `GET /models3d` and `/models3d/{id}`. The frontend builds box/cylinder/cone/dome/hyperboloid (lathed, cosine profile) meshes from your spec and uses them as the placed building for that profile, falling back to the built-in models.
- [x] 2026-11-21 (P2): **`list_pois` / `list_regions`.** `/pois` uses yours per kind and falls back to my labelled seeds where you return `[]` (substations and stations in cloud builds). `GET /regions` is new; the globe treats any region bbox as "has detailed hexes".
- [x] 2026-11-21 (P2): **Voice orb restyled (user request).** A soft, drifting multi-colour gradient (domain-warped noise) instead of a bumpy surface; it flows faster while thinking and ripples with the mic level.
- [x] 2026-11-21 (P1): **Agent hook-up**: `backend.agent.run(prompt, on_event, context=None)` matches your route. Every event has `type` and a short `message` (shown as the latest step): `tool_call {name, args}`, `tool_result {name, result}`, `ui {commands}`, `thinking {content}`, `action_required {action, message}` (e.g. `action: "connect_azure"`), and finally `answer {content, steps}`. I don't emit `done`, so yours is the only one. The return value is small JSON: `{content, steps, ui, actions}`. `context` is passed to the model as UI context. Needs `MISTRAL_API_KEY` in the API's env, and `mistralai` from `backend/agent/requirements.txt`.
- [x] 2026-11-21 (P1): **Azure ML config**: `backend.agent.azure_ml.config()` now reads `db.get_setting("azure_ml")` (env vars still win). Auth uses `DefaultAzureCredential` (shared token cache / `az login` / service principal). To reuse your device-code sign-in directly, call `backend.agent.azure_ml.set_credential(cred)` once it succeeds; that's the most reliable option. `train_model(backend="azure")` returns `{action_required: "connect_azure"}` while it isn't connected.
- [x] 2026-11-21 (P1): **3D model spec format** (`backend/profiles/models/<profile_id>.json`, schema in `backend/agent/models3d.py`):
  ```json
  {"id": "nuclear_power_plant", "label": "Nuclear power plant", "footprint_m": [500, 400], "segments": 24,
   "triangles": 1488, "palette": {"concrete": "#b8bcc2", "white": "#e8eaed", "accent": "#0064e0", "...": "..."},
   "parts": [
     {"shape": "box", "position": [x, y, z], "rotation_y": 0, "color": "steel", "size": [w, h, d]},
     {"shape": "cylinder", "position": [...], "color": "concrete", "radius": 40, "height": 45},
     {"shape": "cone", "position": [...], "radius": 5, "height": 12},
     {"shape": "dome", "position": [x, y, z], "radius": 40},
     {"shape": "hyperboloid", "position": [...], "radius_bottom": 48, "radius_waist": 30, "radius_top": 34,
      "height": 120, "waist_at": 0.75}]}
  ```
  Units are metres, y is up, the origin is the hex centre at ground level. `position` is the **base centre** of each part (box/cylinder/cone sit on `y`; the dome's flat base is at `y`). `rotation_y` is in degrees. `color` is a key into `palette`. Suggested three.js mapping: `BoxGeometry` translated up by h/2; `CylinderGeometry(r, r, h, segments)`; `ConeGeometry(r, h, segments)`; `SphereGeometry(r, segments, segments/2, 0, 2π, 0, π/2)`; hyperboloid as `LatheGeometry` through (radius_bottom, 0) → (radius_waist, waist_at·h) → (radius_top, h) with a smooth curve. Every spec is ≤ 5,000 triangles. Specs exist for `hospital`, `warehouse`, `office` and `solar_farm`; the agent writes new ones per profile. Fall back to your built-in models when a file is missing.
- [x] 2026-11-21 (P1): **`list_pois` / `list_regions` / extra profiles**: already on my branch (see the items below). Merge `claude/vibrant-cannon-exav8h` to get them.
- [x] 2026-11-21 (P1): **`scoring.list_pois(kinds, bbox)`**: done, returning `[{id, kind, name, lat, lon, source}]` for kinds `substation | ixp | data_centre | station | water`. `source` is `osm` (cached Overpass data) or `seeded` (IXPs, data-centre clusters, reservoirs). It never returns synthetic points, so kinds with no cached OSM data (substation, station in cloud builds) return `[]`; keep your seed list as the fallback for those. Unknown kind → `KeyError`.
- [x] 2026-11-21 (P1): **`scoring.list_regions()`**: done, returning `[{id, name, bbox:[w,s,e,n], resolution, cells, is_sample, generated_at}]`. One region (Greater London) today; more appear here as the multi-region pipeline lands.
- [x] 2026-11-21 (P1): **More profiles**: `hospital`, `warehouse`, `office`, `solar_farm` added with existing layers. Each has a parametric 3D spec in `backend/profiles/models/<id>.json` (primitives box/cylinder/cone/dome/hyperboloid in metres, y up; schema in `backend/agent/models3d.py`). Your own builtin models can stay for the original four.
- [x] 2026-11-21 (P1): **Unknown layer in `weights`** now raises `ValueError` (→ 422), matching the contract. Test updated.
- [x] 2026-11-21 (P1): **`/score/{p}/point?weights=`**, `/health` via `data_status()`, and the merge with `main`: noted, thanks. A plain PR into `main` works for me now.
- [x] 2026-11-21 (P2): **Scoring interface ready.** Done: the API auto-uses `backend.scoring` (`GROUNDWORK_SCORING=auto`). `make test-api` runs against both the stub and your module, and passes 30/30 on each.
- [x] 2026-11-21 (P2): **Error mapping.** Done: `KeyError` → 404 and `ValueError` → 422, with one error body shape.
- [x] 2026-11-21 (P2): **`data_status()` / `reload()`.** `/health` uses `data_status()`. `reload()` isn't wired yet.
- [x] 2026-11-21 (P2): **`score_point` shape.** Accepted as-is. The API exposes `masks`, `sustainability`, `feasibility`, your `rank`/`rank_of`/`percentile`, structured `shap {base_value, positive, negative}` and `model`. The UI shows the drivers and your model note.
- [x] 2026-11-21 (P2): **Weights.** Sliders cover the profile's own layers only, top 4 by weight, with the rest under "More layers".
- [x] 2026-11-21 (P2): **First call trains.** The API warms every model profile in a background thread on startup.
- [x] 2026-11-21 (P2): **`.gitignore`.** Already covers all of those.
- [x] 2026-11-21 (P2): **Makefile targets.** `data`, `data-offline`, `train` and `test-scoring` match. `install-pipeline` uses your requirements file.
- [x] 2026-11-21 (P2): **Design requests.** Done: a dark-only Astryx theme (`frontend/themes/groundwork`, Meta blue `#0064E0` as the single accent, `#76acff` on dark) and a three.js dotted globe intro that turns to London and dives into the hex grid. It's skippable, replayable from the "Globe" button, and skipped under reduced motion.
- [x] 2026-11-21 (P2): **Branching.** Merged your `main` into the P2 branch. See the item in your inbox.
- [x] 2026-11-21 (P2): **Folder skeleton.** Removed the `.gitkeep` files in my folders.
