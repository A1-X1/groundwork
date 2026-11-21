"""Template layers defined by YAML in backend/layers/generated/ (no code generation).

The planning agent adds data sources by writing one of these specs; every template is
a fixed, reviewed fetcher with a synthetic fallback, like the hand-written modules.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import _openmeteo, _osm, _synthetic
from ._common import MONTHLY, LayerMeta, cached_json, http_get
from ._geo import grid_xy, idw, lines_to_points, nearest_distance, share_inside

GENERATED_DIR = Path(__file__).parent / "generated"
OSM_SELECTOR = re.compile(r'^(node|way|relation|nwr)(\["[A-Za-z0-9_:]+"((=|~|!=)"[^"\\\\]{0,80}")?\]){1,3}$')
OPENMETEO_DAILY = {
    "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
    "rain_sum", "snowfall_sum", "relative_humidity_2m_mean", "dew_point_2m_mean",
    "wind_speed_10m_mean", "wind_speed_10m_max", "wind_gusts_10m_max", "shortwave_radiation_sum",
    "soil_moisture_0_to_7cm_mean", "soil_temperature_0_to_7cm_mean", "et0_fao_evapotranspiration",
    "cloud_cover_mean", "sunshine_duration",
}
Template = Literal["osm_proximity", "osm_share", "openmeteo_daily", "usgs_earthquakes"]


class LayerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,40}$")
    label: str = Field(min_length=2, max_length=60)
    unit: str = Field(max_length=40)
    kind: Literal["raster", "proximity", "aggregate"]
    description: str = Field(max_length=400)
    template: Template
    params: dict[str, Any] = Field(default_factory=dict)
    added_by: Literal["agent", "human"] = "human"
    is_mask: bool = False

    @field_validator("params")
    @classmethod
    def _check(cls, v: dict[str, Any], info: Any) -> dict[str, Any]:
        t = info.data.get("template")
        if t in ("osm_proximity", "osm_share"):
            sels = v.get("selectors")
            if not isinstance(sels, list) or not 1 <= len(sels) <= 6:
                raise ValueError("osm templates need 1–6 'selectors'")
            for s in sels:
                if not isinstance(s, str) or not OSM_SELECTOR.match(s):
                    raise ValueError(f"invalid Overpass selector {s!r}, e.g. 'nwr[\"power\"=\"plant\"]'")
        elif t == "openmeteo_daily":
            if v.get("variable") not in OPENMETEO_DAILY:
                raise ValueError(f"variable must be one of {sorted(OPENMETEO_DAILY)}")
            if v.get("aggregate", "mean") not in ("mean", "annual_sum", "annual_max"):
                raise ValueError("aggregate must be mean | annual_sum | annual_max")
            if not 1e-6 <= float(v.get("scale", 1.0)) <= 1e6:
                raise ValueError("scale must be a positive unit-conversion factor")
        elif t == "usgs_earthquakes":
            if not 2.5 <= float(v.get("min_magnitude", 4.0)) <= 8:
                raise ValueError("min_magnitude must be 2.5–8")
            if not 1 <= int(v.get("years", 30)) <= 50:
                raise ValueError("years must be 1–50")
            if not 10 <= float(v.get("radius_km", 100)) <= 500:
                raise ValueError("radius_km must be 10–500")
        return v


SOURCES = {
    "osm_proximity": "OpenStreetMap via Overpass API",
    "osm_share": "OpenStreetMap via Overpass API",
    "openmeteo_daily": "Open-Meteo Historical Weather API (ERA5 daily), {a}–{b}",
    "usgs_earthquakes": "USGS ComCat earthquake catalogue (FDSN event API)",
}


def load_specs(directory: Path | None = None) -> list[LayerSpec]:
    directory = directory or GENERATED_DIR
    return [LayerSpec.model_validate(yaml.safe_load(p.read_text())) for p in sorted(directory.glob("*.yaml"))]


def module_for(spec: LayerSpec) -> SimpleNamespace:
    """A module-like object with META, fetch, to_hex and synthetic for the pipeline."""
    src = SOURCES[spec.template].format(a=_openmeteo.NORMALS[0], b=_openmeteo.NORMALS[1])
    meta = LayerMeta(id=spec.id, label=spec.label, unit=spec.unit, kind=spec.kind, description=spec.description,
                     source=src, normalise="identity" if spec.template == "osm_share" else "rank",
                     is_mask=spec.is_mask)
    fetch, to_hex = _TEMPLATES[spec.template](spec)
    return SimpleNamespace(META=meta, fetch=fetch, to_hex=to_hex, synthetic=lambda grid: _synthetic_for(spec, grid))


# ---- templates ---------------------------------------------------------------
def _osm_proximity(spec: LayerSpec):
    def fetch() -> list:
        return _osm.element_lines(_osm.query(f"gen_{spec.id}", spec.params["selectors"]))

    def to_hex(raw: list, grid: pd.DataFrame) -> pd.Series:
        return nearest_distance(grid, lines_to_points(raw, 80))

    return fetch, to_hex


def _osm_share(spec: LayerSpec):
    def fetch() -> list:
        return _osm.element_polygons(_osm.query(f"gen_{spec.id}", spec.params["selectors"]))

    def to_hex(raw: list, grid: pd.DataFrame) -> pd.Series:
        return share_inside(grid, raw)

    return fetch, to_hex


def _openmeteo_daily(spec: LayerSpec):
    var, agg = spec.params["variable"], spec.params.get("aggregate", "mean")
    scale = float(spec.params.get("scale", 1.0))

    def fetch() -> pd.DataFrame:
        start, end = _openmeteo.NORMALS
        raw = _openmeteo._batched(_openmeteo.ARCHIVE_URL, f"daily_{var}_{start}_{end}", {
            "start_date": f"{start}-01-01", "end_date": f"{end}-12-31", "daily": var, "timezone": "UTC"}, batch=3)
        rows = []
        for loc in raw:
            s = pd.Series(np.asarray(loc["daily"][var], dtype=float), index=pd.to_datetime(loc["daily"]["time"]))
            yearly = s.groupby(s.index.year)
            value = {"mean": s.mean(), "annual_sum": yearly.sum().mean(), "annual_max": yearly.max().mean()}[agg]
            rows.append({"lat": loc["latitude"], "lon": loc["longitude"], "value": float(value) * scale})
        return pd.DataFrame(rows)

    def to_hex(raw: pd.DataFrame, grid: pd.DataFrame) -> pd.Series:
        return idw(grid, raw["lat"], raw["lon"], raw["value"])

    return fetch, to_hex


def _usgs(spec: LayerSpec):
    mag = float(spec.params.get("min_magnitude", 4.0))
    years = int(spec.params.get("years", 30))
    radius = float(spec.params.get("radius_km", 100))

    def fetch() -> list[list[float]]:
        from ._common import REGION

        w, s, e, n = REGION["bbox"]
        pad = radius / 111.0 + 0.5
        start = f"{datetime.now(UTC).year - years}-01-01"

        def produce() -> list[list[float]]:
            res = http_get("https://earthquake.usgs.gov/fdsnws/event/1/query", {
                "format": "geojson", "starttime": start, "minmagnitude": mag,
                "minlatitude": s - pad, "maxlatitude": n + pad, "minlongitude": w - pad * 1.6,
                "maxlongitude": e + pad * 1.6, "limit": 20000})
            return [[f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1], f["properties"]["mag"] or mag]
                    for f in res["features"]]

        rid = REGION.get("id", "london")
        name = f"usgs/eq_m{mag}_{years}y_{radius:.0f}km.json" if rid == "london" else \
            f"usgs/{rid}/eq_m{mag}_{years}y_{radius:.0f}km.json"
        return cached_json(name, produce, MONTHLY)

    def to_hex(raw: list[list[float]], grid: pd.DataFrame) -> pd.Series:
        if not raw:
            return pd.Series(0.0, index=grid.index)
        from scipy.spatial import cKDTree

        from ._geo import points_xy

        tree = cKDTree(points_xy([(r[0], r[1]) for r in raw]))
        hits = tree.query_ball_point(grid_xy(grid), radius * 1000)
        return pd.Series([float(len(h)) for h in hits], index=grid.index)

    return fetch, to_hex


_TEMPLATES = {"osm_proximity": _osm_proximity, "osm_share": _osm_share,
              "openmeteo_daily": _openmeteo_daily, "usgs_earthquakes": _usgs}


def _synthetic_for(spec: LayerSpec, grid: pd.DataFrame) -> pd.Series:
    noise = _synthetic.smooth_noise(grid, "gen:" + spec.id)
    if spec.template == "osm_proximity":
        pts = _synthetic.sample_points(grid, spec.id, 40, np.ones(len(grid)), jitter_m=800)
        from ._geo import points_xy

        return nearest_distance(grid, points_xy(pts))
    if spec.template == "osm_share":
        return pd.Series(np.clip(0.1 + 0.1 * noise, 0, 1), index=grid.index)
    if spec.template == "usgs_earthquakes":
        return pd.Series(np.clip(np.round(1 + noise), 0, None), index=grid.index)
    return pd.Series(10 + noise, index=grid.index)
