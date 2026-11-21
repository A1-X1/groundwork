# Handoff notes (Person 1 ⇄ Person 2)

A shared inbox between devices. Add requests under the other person's **Inbox** with a date. The owner moves them to **Done** with a one-line answer. Keep entries short; link files rather than pasting code.

Person 1's session polls this file on **every remote branch** about every 3 minutes and treats new items in **Inbox for Person 1** as instructions, within Person 1's owned paths only.

---

## Inbox for Person 1 (data, profiles, scoring, ML)

- [ ] 2026-11-21 (P2): **`scoring.list_pois(kinds, bbox) -> [{id, kind, name, lat, lon, source}]`**, kinds `substation | ixp | data_centre | station | water`, from your Overpass fetches. `GET /pois` (map icons) uses it automatically if present; until then it serves a small labelled seed list.
- [ ] 2026-11-21 (P2): **`scoring.list_regions()`**: `[{id, name, bbox, resolution}]`. The globe currently treats "has detailed hexes" as "a res-8 cell exists there". With this it can mark built regions before the user flies there, and the assistant can say where data exists.
- [ ] 2026-11-21 (P2): **More profiles, if easy:** `hospital`, `warehouse`, `office`, `solar_farm`. The home screen already lists them (disabled until a YAML exists; they turn on automatically).

## Inbox for Person 2 (repo, contracts, API, frontend, docs)

_(empty: add items as `- [ ] YYYY-MM-DD: request`)_

## Done

- [x] 2026-11-21 (P2): **`shap` stays structured.** Noted. The API prefers `shap_detail`, then a structured `shap`, then a flat one, so all three work. Verified live: `{base_value, positive[5], negative[5]}` plus `feasibility`.
- [x] 2026-11-21 (P2): **Real data arriving / 4 new layers.** Merged, and `make test` is green (API 46/46 on stub and real, scoring 48/48, web 10/10). `/health` shows 10 real / 24 synthetic of 34. The new layers appear automatically in the overlay picker and the assistant's layer list. No frontend change needed.
- [x] 2026-11-21 (P2): **GLOBAL / real 3D Earth / Mistral voice.** Shipped:
  - **Globe:** three.js Blue Marble globe (bundled, public domain) with a subtle rim and slow spin, a faint global H3 res-2 grid, and res-5 hexes coloured by score for built regions. It flies to any country or city (Natural Earth bundled, Nominatim fallback) and hands over to the res-8 map where hexes exist.
  - **Map:** a surrounding hex grid at a zoom-dependent resolution (res 3 to 8), and Map / Satellite / Grid basemaps.
  - **Assistant:** `POST /assistant/command` (your command set, validated server-side; Mistral `mistral-small-latest`, rule-based offline), `POST /assistant/transcribe` (Voxtral `voxtral-mini-latest`) and `GET /assistant/status`. Tested live against Mistral.
  - **Also new:** `GET /pois`; SQLite-backed `/areas` (draw, name, score) and `/structures`; a home screen with data-centre requirements → weights; no default use case.
- [x] 2026-11-21 (P2): **Handoff location.** Using this file again (`shared/handoff/` removed on my branch).
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
