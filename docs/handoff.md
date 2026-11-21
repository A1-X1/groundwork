# Handoff notes (Person 1 ⇄ Person 2)

A shared inbox between devices. Add requests under the other person's **Inbox** with a date. The owner moves them to **Done** with a one-line answer. Keep entries short; link files rather than pasting code.

Person 1's session polls this file on **every remote branch** about every 3 minutes and treats new items in **Inbox for Person 1** as instructions, within Person 1's owned paths only.

---

## Inbox for Person 1 (data, profiles, scoring, ML)

- [ ] 2026-11-21 (P2): **Agent hook-up is ready on the API side.** `POST /agent/run` imports `backend.agent` and calls `run(prompt, on_event, context=...)` (`context` only when the UI sends one) in a worker thread, streaming each `on_event(dict)` as SSE (`event: <type>`, `data: <json>`). It ends with `{"type": "done", "result": <your return value>}` or `{"type": "error", "message"}`. Emit `{"action": "connect_azure"}` and the UI opens Connections. While the module is missing it returns 503 `agent_unavailable`. A test with a fake `backend.agent` covers this contract (`backend/tests_api/test_agent.py`). Please keep `message` on step events: the UI shows the latest one.
- [ ] 2026-11-21 (P2): **Azure ML config for your training step:** `from backend.api import db; db.get_setting("azure_ml")` gives `{subscription_id, resource_group, workspace}` or `None`. Sign-in is the device-code flow via `azure-identity` in the API process; use `DefaultAzureCredential` / the shared token cache on your side. No secrets are stored in SQLite.
- [ ] 2026-11-21 (P2): **3D model spec:** send the format when ready (primitives box/cylinder/cone/dome/hyperboloid with size, position and material?). The building layer is parametric already (`frontend/src/map/buildings.ts`), so a JSON → mesh builder is quick.
- [ ] 2026-11-21 (P2): `scoring.list_pois(kinds, bbox)`, `scoring.list_regions()` and extra profiles (`hospital`, `warehouse`, `office`, `solar_farm`): still welcome (see the earlier note). Nothing is blocked.

## Inbox for Person 2 (repo, contracts, API, frontend, docs)

_(empty: add items as `- [ ] YYYY-MM-DD: request`)_

## Done

- [x] 2026-11-21 (P2): **Voice orb.** `frontend/src/map/VoiceOrb.tsx`: one shader-displaced icosphere (simplex noise, accent on dark, fresnel rim, no post-processing). It breathes when idle, ripples and grows with mic RMS while listening, swirls while thinking, and pulses with a speech envelope while speaking. Tap to talk, hold for push-to-talk, drag to spin; keyboard Enter/Space; reduced motion damps it. Speech-to-text is Voxtral via `POST /assistant/transcribe` (`VOXTRAL_MODEL`, default `voxtral-mini-latest`; set `voxtral-small-latest` in `.env` if you prefer), with the browser's recognition as a fallback. Typed commands stay in the command bar.
- [x] 2026-11-21 (P2): **Planning agent, P2 side.** `POST /agent/run` (SSE, see your inbox). The orb and command bar send anything that isn't a UI command to the agent; on 503 they fall back to the assistant's reply. There is a **Connections** dialog (top bar): Mistral status, plus an Azure ML workspace (`PUT/DELETE /connections/azure`) and device-code **Sign in** (`POST /connections/azure/login`, polled via `GET /connections`). The agent's `connect_azure` action opens it. `PAN_*` and the other UI commands are unchanged.
- [x] 2026-11-21 (P2): **OSM downloads.** Noted. `/pois` keeps serving the labelled seed list until real points arrive.
- [x] 2026-11-21 (P2): **`shap` stays structured.** Noted. The API prefers `shap_detail`, then a structured `shap`, then a flat one. Verified live.
- [x] 2026-11-21 (P2): **Real data arriving / 4 new layers.** Merged, and `make test` is green. `/health` shows 10 real / 24 synthetic of 34. The new layers appear automatically in the overlay picker.
- [x] 2026-11-21 (P2): **GLOBAL / real 3D Earth / Mistral voice.** Shipped: textured three.js globe with a global H3 grid and fly-to/hand-over, a surrounding grid and Map/Satellite/Grid basemaps on the map, `/assistant/command`, `/assistant/transcribe` (Voxtral), `/pois`, SQLite `/areas` and `/structures`, a home screen with data-centre requirements, and no default use case.
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
