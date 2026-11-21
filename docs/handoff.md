# Handoff notes (Person 1 ⇄ Person 2)

A shared inbox between devices. Add requests under the other person's **Inbox** with a date. The owner moves them to **Done** with a one-line answer. Keep entries short; link files rather than pasting code.

Person 1's session polls this file on its branch about every 3 minutes and treats new items in **Inbox for Person 1** as instructions, within Person 1's owned paths only.

---

## Inbox for Person 1 (data, profiles, scoring, ML)

_(empty — add items as `- [ ] YYYY-MM-DD: request`)_

## Inbox for Person 2 (repo, contracts, API, frontend, docs)

- [ ] 2026-11-21: **Scoring interface is ready.** `backend/scoring/__init__.py` implements contract §5.1 against `data/sample/grid.parquet` (2,654 London res-8 hexes, 30 layers). Swap your stub for `import backend.scoring as scoring`.
- [ ] 2026-11-21: **Error mapping.** `KeyError` → 404 (unknown profile/layer, or a point outside London); `ValueError` → 422 (bad weights, bbox, lat/lon).
- [ ] 2026-11-21: **Extra functions (additive, not in the contract):** `scoring.data_status()` gives `/health` the data dir, `is_sample`, `generated_at`, `cells`, `real_layers` and `synthetic_layers`. `scoring.reload()` drops caches.
- [ ] 2026-11-21: **`score_point` shape** (not frozen by the contract; tell me if you want changes): `profile, h3, lat, lon, score, masked, masks[], sustainability_score, feasibility_score, rank (1 = best, null if masked), rank_of, percentile, weights{}, breakdown{}, layers[{id,label,unit,value,raw,weight,better,contribution}], raw{all layers}, values{all layers}, shap (null | {base_value, positive[≤5], negative[≤5]} of {layer,label,value,raw}), model (null | {type, positives, auc_spatial_cv, n_positives, positives_synthetic, note})`.
- [ ] 2026-11-21: **Weights.** Overrides may only target the profile's own layers. Another layer with weight 0 is ignored; non-zero raises `ValueError`, because a direction is needed. `list_profiles()` lists layers sorted by weight, highest first, so take the first N for the visible sliders.
- [ ] 2026-11-21: **First call per model profile** (`data_centre`, `house`) trains in memory (about 1 s) unless `make train` has run. Consider warming it on API startup.
- [ ] 2026-11-21: **`.gitignore` needs:** `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `node_modules/`, `.env`. `data/.gitignore` already covers `data/raw`, `data/processed` and `data/sample/models`.
- [ ] 2026-11-21: **Makefile targets:** `data: python -m backend.pipeline.run`, `train: python -m backend.scoring.train`, and tests via `python -m pytest backend/tests_scoring`. Install with `uv pip install -r backend/pipeline/requirements.txt`.
- [ ] 2026-11-21: **Design requests from the user (frontend is yours):**
  1. A minimal theme with a dark background in the style of Meta's product UI (Astryx dark mode, one accent colour).
  2. **The world as a 3D globe rendered with three.js**, zooming into London's hex grid.
- [ ] 2026-11-21: **Branching.** P1 work is on `claude/vibrant-cannon-exav8h`, which was the first push to an empty repo. If you create `main` separately the histories won't share a root, so either branch `main` from this commit or tell me and I'll rebase onto yours.

## Done

_(nothing yet)_
