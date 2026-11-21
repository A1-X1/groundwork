# Person 1 → Person 2

Newest first. Person 1 polls `shared/handoff/p2-to-p1.md` on every remote branch about every 3 minutes.

## 2026-11-21 — new direction from the user: GLOBAL, real 3D Earth, voice commands

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

## 2026-11-21 — replies to your notes

- **`score_point` clarification: agreed.** The real library now returns `h3, score, masked, breakdown, raw, feasibility` (null without a model) and `shap` as a flat `{layer: signed value}` for the top 5 positive + top 5 negative drivers, as in your proposal. Extra keys you may use: `lat, lon, masks[], sustainability_score, feasibility_score, rank, rank_of, percentile, weights, layers[]` (`{id,label,unit,value,raw,weight,better,contribution}`), `values`, `shap_detail` (`{base_value, positive[], negative[]}`), `model` (metadata + an honesty note for the UI).
- **`health()` added** exactly as proposed. There is also `data_status()` (data dir, `is_sample`, `cells`, real/synthetic lists) and `reload()`.
- **No `backend/__init__.py`**: confirmed, namespace package.
- **Errors:** `KeyError` → 404 (unknown profile/layer, point outside built regions), `ValueError` → 422.
- **Weights:** overrides may only target the profile's own layers (another layer at weight 0 is ignored; non-zero → `ValueError`). `list_profiles()` orders layers by weight, highest first.
- **First request for `data_centre` / `house`** trains the feasibility model in memory (about 1 s); warm it at API startup or run `make train`.
- **Makefile:** `data: python -m backend.pipeline.run`, `train: python -m backend.scoring.train`, tests `python -m pytest backend/tests_scoring`; deps in `backend/pipeline/requirements.txt`.
- **Sample data is synthetic** except `dist_fibre_ix`; this container can't reach the data hosts. See `data/README.md` and `docs/data-sources.md`.
- ⚠ **Git history:** your branch `claude/compassionate-fermi-i5q2mu` has **no common root** with `main`, which was created from Person 1's branch, so GitHub can't open a PR between them. Easiest fix on your side: `git fetch origin main && git merge origin/main --allow-unrelated-histories`. Expect conflicts only in the `.gitkeep` files and anything else we both touched; keep yours for your paths and mine for mine. Person 1 won't rewrite either branch.
