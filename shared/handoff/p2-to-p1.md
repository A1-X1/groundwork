# Person 2 → Person 1

## 2026-11-21 — repo scaffolded, API live against a stub

- `shared/contracts/` is committed. One **proposed clarification** for you to confirm: the
  `score_point` return keys (`h3, score, masked, breakdown, raw, feasibility?, shap?`) are written
  down in `scoring_interface.md` under "proposed clarification". Reply in `p1-to-p2.md`.
- **Proposed optional extension:** `backend.scoring.health() -> {"data_generated_at": iso str | None,
  "layers": {layer_id: "real" | "synthetic"}}`. `GET /health` uses it if present, otherwise reports
  every layer as `unknown`. Not required.
- The API auto-switches: if `backend.scoring` imports and exposes the five functions it is used;
  otherwise `backend/api/stub_scoring.py` (synthetic London grid) is used.
  Force with `GROUNDWORK_SCORING=real|stub`.
- Profile/layer ids in the stub match §6/§7 of the brief so the frontend works with either.
- Please don't create `backend/__init__.py`; the API relies on `backend` being a namespace package
  (fine if you do need one — just tell me).
