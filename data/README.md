# data/

| Path | Committed | What |
|---|---|---|
| `raw/` | no | Download cache for every source (`raw/osm/`, `raw/open_meteo/`, `raw/police/`, …) plus files you download by hand (see `docs/data-sources.md`). |
| `processed/` | no | `grid.parquet`, `layers.json`, `build.json`, `models/` from `python -m backend.pipeline.run` and `python -m backend.scoring.train`. |
| `sample/` | yes | An offline build (~1 MB) so a fresh clone works with no downloads. The scoring library uses it whenever `processed/` is missing. |

## Files

- **`grid.parquet`**: one row per H3 res-8 hex. Columns: `h3`, one 0–1 column per layer id (percentile rank within the region; higher means more of the thing, whatever the direction), and `raw_<layer_id>` in original units.
- **`layers.json`**: the `list_layers()` payload (id, label, unit, kind, description, source, min, max).
- **`build.json`**: build time, region, resolution, cell count, and for every layer `status: real | synthetic` with a reason, plus `uses_synthetic` when a real layer depends on a synthetic one.

## Building

```bash
python -m backend.pipeline.run                       # real sources where reachable
python -m backend.pipeline.run --layers crime_rate   # rebuild one layer, keep the rest
python -m backend.pipeline.run --offline             # cache-only; synthetic for the rest
python -m backend.pipeline.run --offline --out data/sample   # refresh the committed sample
python -m backend.scoring.train                      # feasibility models → <data dir>/models/
```

Override the data directory the API reads with `GROUNDWORK_DATA_DIR=/path`.

**The committed sample is synthetic** (except `dist_fibre_ix`, a seeded list of real IXP sites). The patterns are London-shaped (heat island, Thames floodplain, east/west deprivation and price gradients) but they are not measurements. Check `build.json` or `/health` before treating any number as real.
