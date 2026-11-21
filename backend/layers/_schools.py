"""Schools from GIAS (Get Information About Schools), falling back to OSM amenity=school."""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from . import _osm
from ._common import SourceUnavailable, require_file

GIAS_HINT = ("Download 'All establishment data' (edubasealldata*.csv) from "
             "https://get-information-schools.service.gov.uk/Downloads and save it as "
             "data/raw/gias/edubasealldata.csv")
GOOD = {"Outstanding", "Good"}
RATED = GOOD | {"Requires improvement", "Inadequate", "Serious Weaknesses", "Special Measures"}


def bng_to_wgs84(easting: pd.Series, northing: pd.Series) -> tuple[pd.Series, pd.Series]:
    from pyproj import Transformer

    tf = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    lon, lat = tf.transform(easting.to_numpy(), northing.to_numpy())
    return pd.Series(lon, index=easting.index), pd.Series(lat, index=easting.index)


@lru_cache(maxsize=1)
def schools() -> pd.DataFrame:
    """Open schools in/near London: columns lon, lat, phase ('primary'|'secondary'), rating."""
    try:
        return _gias()
    except SourceUnavailable:
        return _osm_schools()


def _gias() -> pd.DataFrame:
    path = require_file("gias", "edubasealldata.csv", hint=GIAS_HINT)
    df = pd.read_csv(path, encoding="latin-1", low_memory=False)
    df = df[df["EstablishmentStatus (name)"] == "Open"].dropna(subset=["Easting", "Northing"])
    df = df[(df["Easting"] > 500_000) & (df["Easting"] < 565_000)
            & (df["Northing"] > 150_000) & (df["Northing"] < 205_000)]
    lon, lat = bng_to_wgs84(df["Easting"], df["Northing"])
    phase = df["PhaseOfEducation (name)"].fillna("")
    out = pd.DataFrame({
        "lon": lon, "lat": lat,
        "phase": phase.map(lambda p: "secondary" if p in {"Secondary", "16 plus", "All-through"}
                           else ("primary" if p in {"Primary", "Middle deemed primary", "Nursery"}
                                 else "other")),
        "rating": df.get("OfstedRating (name)", pd.Series(index=df.index, dtype=object)),
    })
    return out.reset_index(drop=True)


def _osm_schools() -> pd.DataFrame:
    els = _osm.query("schools", ['nwr["amenity"="school"]'], geometry=False)
    rows = []
    for el in els:
        pt = _osm.element_points([el])
        if not pt:
            continue
        name = el.get("tags", {}).get("name", "")
        secondary = any(k in name for k in ("High School", "Academy", "College", "Secondary", "Grammar"))
        rows.append({"lon": pt[0][0], "lat": pt[0][1],
                     "phase": "secondary" if secondary else "primary", "rating": None})
    if not rows:
        raise RuntimeError("no schools returned from OSM")
    return pd.DataFrame(rows)
