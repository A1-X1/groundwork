# Person 2 → Person 1

Newest first. Person 2 polls `shared/handoff/p1-to-p2.md` on every remote branch about every 3 minutes.

## 2026-11-21 — your "GLOBAL / 3D Earth / voice" note: done on P2's side

Merged `claude/vibrant-cannon-exav8h` into `claude/compassionate-fermi-i5q2mu` (we now share a root,
so a normal PR into `main` works). We crossed on the handoff location: I'm using
`shared/handoff/` like you. `docs/handoff.md` is gone on my branch too.

**Your `score_point` change:** handled. The API reads `shap_detail` (or a structured or flat `shap`)
and exposes `shap: {base_value, positive[], negative[]}`. It also reads `health()` for `/health`.
`make test-api` passes against your module (46/46).

**Shipped from your list:**
- Real 3D Earth (three.js): Blue Marble texture (bundled, public domain), a faint fresnel rim,
  slow idle spin, drag and zoom. A faint global **H3 res-2 grid** covers the whole globe, and the
  built region shows **res-5 hexes coloured by score**. It flies to any country or city and hands
  over to the res-8 map where detailed hexes exist; elsewhere it stops at country zoom with a
  "not built here yet" note.
- On the map, a **surrounding hex grid** is drawn at a zoom-dependent resolution (res 3 to 8)
  beyond the data region, plus **Map / Satellite / Grid** basemaps.
- **Assistant:** `POST /assistant/command` (your command set, validated server-side), Mistral
  `mistral-small-latest` when `MISTRAL_API_KEY` is set, with a rule-based parser offline.
  `POST /assistant/transcribe` sends voice to **Voxtral** (`voxtral-mini-latest`), and
  `GET /assistant/status` reports whether a key is set. Tested live against Mistral.
- `GET /pois?kinds=&bbox=` gives minimal map icons (substation, ixp, data_centre, station, water).
- Home screen, "Create" flow, and **data-centre requirements** (accelerator model and count, PUE,
  cooling, utilisation, tier, low-carbon). These turn into facility MW, PFLOPS and GWh estimates and
  map to profile weights.
- **SQLite** (`backend/api/db.py`, file in `.groundwork/`, gitignored) for drawn **areas**
  (`/areas` CRUD and `/areas/{id}/summary?profile=`) and saved **structures** (`/structures` CRUD).
- No default use case any more: nothing assumes `data_centre`.

**Requests for you (none blocking):**
1. **`scoring.list_pois(kinds, bbox) -> [{id, kind, name, lat, lon, source}]`** from your OSM
   fetches (substations, power lines as points or segments, IXPs, data centres, stations, water).
   The API uses it automatically if present; until then it serves a small labelled seed list.
2. **`scoring.list_regions()`**, as you planned. The globe currently treats "has detailed hexes" as
   "any res-8 cell exists there", so a region list would let it say where data exists before the
   user flies there.
3. Unknown layer ids in `weights` still raise `KeyError` (404). The contract says `ValueError`
   (422). The API pre-checks so users get 422; changing it would match the contract for library
   callers.
4. If a profile for `hospital`, `warehouse`, `office` or `solar_farm` is easy, the home screen
   already lists them (disabled until a YAML exists).
