# Handoff notes (Person 1 ⇄ Person 2)

A shared inbox between devices. Add requests under the other person's **Inbox** with a date. The owner moves them to **Done** with a one-line answer. Keep entries short; link files rather than pasting code.

Person 1's session polls this file on **every remote branch** about every 3 minutes and treats new items in **Inbox for Person 1** as instructions, within Person 1's owned paths only.

---

## Inbox for Person 1 (data, profiles, scoring, ML)

_(empty: add items as `- [ ] YYYY-MM-DD: request`)_

## Inbox for Person 2 (repo, contracts, API, frontend, docs)

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
