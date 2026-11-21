# Handoff notes (Person 1 ⇄ Person 2)

A shared inbox between devices. Add requests under the other person's **Inbox** with a date. The owner moves them to **Done** with a one-line answer. Keep entries short; link files rather than pasting code.

Person 1's session polls this file on **every remote branch** about every 3 minutes and treats new items in **Inbox for Person 1** as instructions, within Person 1's owned paths only.

---

## Inbox for Person 1 (data, profiles, scoring, ML)

_(empty: add items as `- [ ] YYYY-MM-DD: request`)_

## Inbox for Person 2 (repo, contracts, API, frontend, docs)

- [ ] 2026-11-21 (P1): **Voice assistant UI: an interactive orb** (user request). A sphere in three.js with a smooth, flowing surface (a shader-displaced icosphere or soft gradient blob, in the spirit of modern voice-agent orbs, but our own design). It breathes slowly when idle, ripples and grows with mic input level while listening, swirls while thinking, and pulses with the TTS amplitude while speaking. Tap or press-and-hold to talk, hover to highlight, drag to spin it slightly. Use the single accent colour on the dark theme, respect `prefers-reduced-motion`, and keep it light (one mesh, no post-processing). Speech-to-text can use Mistral `voxtral-small-latest`; a Mistral key is already set up for P1's agent work.
- [ ] 2026-11-21 (P1): **Planning agent (user request), in progress on P1's side in `backend/agent/`.** A Mistral tool-calling agent. Given e.g. "I'm looking for building a nuclear power plant", it:
  1. identifies the use case
  2. picks existing layers
  3. adds new data sources from a vetted registry of free APIs as YAML layers (`backend/layers/generated/`, fixed templates such as OSM proximity, Open-Meteo daily and USGS seismic; no generated code)
  4. writes and validates a profile YAML
  5. writes a parametric three.js model spec
  6. builds the new layers
  7. trains the feasibility model in **Azure ML**, or locally if Azure isn't connected

  P2 asks, once P1 publishes the Python interface (`backend.agent.run(prompt, on_event)` with streamed step events):
  - `POST /agent/run` (SSE stream of steps and a final summary). The voice orb and the command palette both call it.
  - A **Connections** screen with Mistral status and **Sign in to Azure ML** (subscription, resource group, workspace; browser or device-code login). When the agent returns `{"action": "connect_azure"}`, prompt the user to sign in, then resume.
  - Render `backend/profiles/models/<profile>.json` parametric 3D specs as the placeable building (primitives: box, cylinder, cone, dome, hyperboloid cooling tower; spec format to follow).
  - Keep `PAN_COUNTRY` / `PAN_CITY` etc. (earlier item) as the agent's UI commands.
- [ ] 2026-11-21 (P1): **OSM downloads.** Public Overpass servers time out from the cloud container, and Geofabrik extracts also drop there, so OSM layers stay synthetic in cloud builds for now. Both usually work from a laptop. Nothing for you to do.

- [ ] 2026-11-21 (P1): **`shap` shape stays structured:** `{base_value, positive[≤5], negative[≤5]}` of `{layer, label, value, raw}`, as your UI uses it. For about 30 minutes my branch briefly returned a flat dict there; that is reverted. The flat form is available as `shap_flat`. `feasibility` (null without a model) is also returned.
- [ ] 2026-11-21 (P1): **Real data is arriving.** This environment can now reach the free data APIs. 10 of 34 layers are real in `data/sample` (elevation, slope, 2025 hourly weather layers, IXPs); the full online build is in progress. There are 4 new layers: `precipitation_annual`, `soil_moisture_mean`, `evapotranspiration_annual`, `temp_trend_decade` (10-year ERA5 normals). Endpoint status, sign-ups and the refresh policy are in `docs/data-sources.md`. The API never calls data sources; `make data` once a day is enough (caches expire per source).
- [ ] 2026-11-21 (P1): **User direction: GLOBAL, real 3D Earth, Mistral voice commands.**

  **1. Not just London: the product is global.** Person 1 is making the data side multi-region (details below). Frontend asks for you:
  - **A real 3D Earth in three.js**: textured globe (day imagery + subtle atmosphere rim), starting zoomed out and rotating slowly. It flies to a country or city and hands over to the hex map at city zoom. `globe.gl` / `three-globe` are fine helpers, or raw three.js with `SphereGeometry` + GIBS/Blue Marble textures. Keep the minimal Meta-style dark UI (Astryx dark, one accent).
  - **Hex layer at every zoom.** Coarse H3 (res 3–5) on the globe, res 8 when zoomed into a built region. Same `/score` and `/layers` calls with `bbox`; I'll make the scoring library pick regions by bbox, so the contract shape doesn't change.

  **2. Mistral voice / natural-language commands (user plans to add).** Proposed command set. The LLM turns speech or text into a JSON list of these; the frontend executes them. Please own the parser endpoint (e.g. `POST /assistant/command`, with the Mistral key server-side in `.env`):

  | Command | Args | Effect |
  |---|---|---|
  | `PAN_COUNTRY` | `name` | Fly the globe to a country's bounds |
  | `PAN_CITY` | `name`, `country?` | Fly to a city (geocoded) |
  | `PAN_REGION` | `bbox` or `name` | Fly to an arbitrary area |
  | `ZOOM` | `direction: in\|out`, `levels?` | Zoom |
  | `RESET_VIEW` | none | Back to the whole globe |
  | `ROTATE_GLOBE` | `on\|off` | Idle spin |
  | `SET_PROFILE` | `id` (data_centre, house, school, mine, …) | Switch use case |
  | `SET_OVERLAY` | `layer` (suitability, thermal, height, flood, crime, air, or any layer id) | Switch overlay |
  | `SET_WEIGHT` | `layer`, `weight` | Move a slider (re-scores) |
  | `RESET_WEIGHTS` | none | Profile defaults |
  | `SHOW_TOP_SITES` | `n?`, `profile?` | Highlight and list the best hexes in view |
  | `SELECT_PLACE` | `name` or `lat,lon` | Open the detail panel there |
  | `PLACE_SITE` | `profile?`, `name` or `lat,lon` | Drop a three.js building |
  | `REMOVE_SITE` / `RENAME_SITE` | `id`, `name?` | Manage placed sites |
  | `COMPARE_SITES` | `ids[2]` | Side-by-side |
  | `COMPARE_USE_CASES` | `profiles[]`, place | Calls `/compare` |
  | `EXPLAIN` | `place?` | Spoken "why this spot" from breakdown + SHAP |
  | `TOGGLE_MASKS` / `TOGGLE_TERRAIN` | `on\|off` | Display toggles |
  | `HELP` | none | List what it can do |

  Geocoding for `PAN_COUNTRY` / `PAN_CITY`: Natural Earth admin-0 bounds (bundled, public domain) for countries, and Nominatim or GeoNames for cities. Person 1 will expose `scoring.list_regions()` so the assistant knows where detailed hexes exist.

  **3. Free global data endpoints Person 1 is moving to** (most need no key; ⚠ = free key or manual download):
  - Climate and air: Open-Meteo Historical Weather and Air Quality (global, no key, non-commercial use).
  - Elevation: Open-Meteo Elevation (Copernicus GLO-90), or Copernicus DEM COGs on AWS Open Data.
  - Population: WorldPop (100 m GeoTIFF, REST API) / JRC GHSL GHS-POP.
  - Infrastructure (stations, substations, power lines, roads, water, parks, schools, data centres): OpenStreetMap via Overpass. Night lights: NASA Black Marble.
  - Hazards: JRC global river flood maps; WRI Aqueduct floods and water stress; USGS earthquake catalogue API (new layer).
  - Protected land: WDPA / Protected Planet (⚠ free token, or monthly download).
  - Grid carbon intensity per country: Our World in Data energy CSV (GitHub, no key); Ember; Electricity Maps (⚠ free tier key).
  - Minerals for the mine profile: USGS MRDS.
  - Boundaries: Natural Earth (public domain), geoBoundaries API.
  - Globe imagery for you: NASA GIBS WMTS / Blue Marble (public domain).
  - Country-specific extras such as UK crime, IMD and Land Registry stay as optional per-region layers.

## Done

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
