# Handoff notes (Person 1 ⇄ Person 2)

A shared inbox between devices. Add requests under the other person's **Inbox** with a date. The owner moves them to **Done** with a one-line answer. Keep entries short; link files rather than pasting code.

Person 1's session polls this file on its branch about every 3 minutes and treats new items in **Inbox for Person 1** as instructions, within Person 1's owned paths only.

---

## Inbox for Person 1 (data, profiles, scoring, ML)

- [ ] 2026-11-21: **Unknown layer in `weights` raises `KeyError` (→ 404).** Contract §5.1 says bad weights are `ValueError` (→ 422). The API now pre-checks weight keys against the profile and returns 422 either way, so nothing is broken. Raising `ValueError` would match the contract for direct library callers too.
- [ ] 2026-11-21: **FYI: `GET /score/{p}/point` now takes `?weights=layer:w,layer:w`** and passes it to `score_point(..., weights=)`, so the detail panel matches the sliders. This is additive, with no contract change.
- [ ] 2026-11-21: **FYI: `/health`** reads `data_status()` (`generated_at`, `real_layers`, `synthetic_layers`).
- [ ] 2026-11-21: **Branching.** `claude/compassionate-fermi-i5q2mu` (P2) now **merges your `main`** with `--allow-unrelated-histories`, so it shares your root. A plain merge PR into `main` will work. No rebase needed on your side.

## Inbox for Person 2 (repo, contracts, API, frontend, docs)

_(empty: add items as `- [ ] YYYY-MM-DD: request`)_

## Done

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
