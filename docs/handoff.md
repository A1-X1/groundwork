# Handoff notes (Person 1 ⇄ Person 2)

A shared inbox between devices. Add requests under the other person's **Inbox** with a date. The owner moves them to **Done** with a one-line answer. Keep entries short; link files rather than pasting code.

Person 1's session polls this file on **every remote branch** about every 3 minutes and treats new items in **Inbox for Person 1** as instructions, within Person 1's owned paths only.

---

## Inbox for Person 1 (data, profiles, scoring, ML)

_(empty: add items as `- [ ] YYYY-MM-DD: request`)_

## Inbox for Person 2 (repo, contracts, API, frontend, docs)

_(empty: add items as `- [ ] YYYY-MM-DD: request`)_

## Done

- [x] 2026-11-21 (P2): **Voice agent from the very start.** The home screen now has the command bar ("or describe anything you want to build") and the voice assistant box. On the home screen every prompt goes straight to `POST /agent/run` with `context: {screen: "home", view: "home", structures: [names], profile, overlay, selected_h3}`. On the map, planning-like prompts still go to the agent and simple ones to the fast assistant. New `ui` commands are handled: `OPEN_CREATE`, `GO_HOME`, `CREATE_STRUCTURE {profile, name}` (refetches `/profiles` first, saves the structure in SQLite and opens the map with that profile), `OPEN_STRUCTURE {name}`, `SHOW_MODEL {profile}` (a dialog with a turning three.js preview of `/models3d/{profile}` or the built-in model) and `SHOW_PROGRESS {title, step}` (a floating card with a 5-step stepper: choosing data → profile → 3D model → training → results; `step` may be an index or a name; your `tool_call` names also advance it). The card hides when the run ends. `ui` commands from one run execute in order, so `CREATE_STRUCTURE` completes before later commands. The stream stays open for long runs and shows each `message`. Verified live: "show me the 3D model for a wind farm" from the home screen led to `get_catalog` and `SHOW_MODEL wind_farm`, and the preview opened (~20 s). `/assistant/command` also accepts the six new command types.

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
