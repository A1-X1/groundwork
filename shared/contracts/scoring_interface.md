# Scoring interface contract

**Status: frozen.** Neither side changes this file without both people agreeing.
Person 1 implements it in `backend/scoring/__init__.py`; Person 2 (the API) calls it.

## Module: `backend.scoring`

```python
def list_profiles() -> list[dict]:
    """[{"id": "house", "label": "House", "description": str,
         "layers": [{"id": str, "weight": float, "better": "higher"|"lower"}],
         "masks": [str], "has_model": bool}]"""

def list_layers() -> list[dict]:
    """[{"id": str, "label": str, "unit": str, "kind": "raster"|"proximity"|"aggregate",
         "description": str, "source": str, "min": float, "max": float}]"""

def get_layer(layer_id: str, bbox: tuple[float, float, float, float] | None = None) -> list[dict]:
    """[{"h3": str, "value": float (0–1 normalised), "raw": float}]"""

def score(profile_id: str,
          weights: dict[str, float] | None = None,      # overrides profile weights
          bbox: tuple[float, float, float, float] | None = None  # (min_lon, min_lat, max_lon, max_lat)
          ) -> list[dict]:
    """Returns cells as in score_response (see score_response.schema.json, $defs/cell)."""

def score_point(profile_id: str, lat: float, lon: float,
                weights: dict[str, float] | None = None) -> dict:
    """Single cell result for the hex containing (lat, lon), including breakdown,
    raw layer values, and (if model) shap values."""
```

### Errors

| Raised by scoring | Meaning | API maps to |
|---|---|---|
| `KeyError` | unknown profile id or layer id | `404 Not Found` |
| `ValueError` | bad weights (negative, unknown layer, all zero, …) or bad bbox | `422 Unprocessable Entity` |

### Conventions

- `bbox` is always `(min_lon, min_lat, max_lon, max_lat)` in WGS84 degrees.
- H3 ids are res-8 cell strings (`h3` v4, e.g. `"88195da49bfffff"`).
- Weights passed to `score` / `score_point` override the profile's weights for the given layer ids;
  the scorer renormalises so they sum to 1.
- `score` is `null` and `masked` is `true` for cells hit by any of the profile's masks.
- `breakdown[layer] = weight × (normalised_value − regional_mean)`, direction-corrected
  (positive = this layer pushes the cell above the regional average).
- Final score = `sustainability_score × feasibility_score` (feasibility = 1.0 when the profile has no model).

### `score_point` return shape (proposed clarification — pending Person 1 agreement)

`score_point` is not covered by `score_response.schema.json`. The API reads these keys
and treats any missing optional key as absent:

```python
{
  "h3": str,
  "score": float | None,
  "masked": bool,
  "breakdown": dict[str, float],
  "raw": dict[str, float],            # raw layer values in original units, keyed by layer id
  "feasibility": float | None,        # optional; present when the profile has a model
  "shap": dict[str, float] | None,    # optional; top drivers, signed
}
```

## Data files (internal to Person 1, documented for transparency)

- `data/processed/grid.parquet`: column `h3` (str) + one column per layer id
  (float 0–1, direction-agnostic: higher = more of the thing) + `raw_<layer_id>` (float, original units).
- `data/processed/layers.json`: the `list_layers()` metadata.
- `data/sample/grid.parquet`: small committed copy for the offline demo.
