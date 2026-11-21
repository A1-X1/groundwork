"""Map points of interest per region (the icons in the map key), from free global datasets.

    python -m backend.pipeline.pois --region uk      # or: all

Sources (downloaded once into data/raw/pois/, all free, no key):
- station:      UK National Rail stations (github.com/davwheat/uk-railway-stations, from NaPTAN/ORR)
- power_plant:  WRI Global Power Plant Database (CC BY 4.0), with fuel and capacity
- airport:      OurAirports (public domain), large and medium airports
- port:         Natural Earth 10 m ports (public domain)
- water:        Natural Earth 10 m lakes and reservoirs (public domain)
- data_centre / ixp: PeeringDB facilities; a facility hosting an exchange is an `ixp`
Points are kept only if they fall in one of the region's land hexes, so nothing sits at sea.
Output: data/processed/regions/<region>/pois.parquet (id, kind, name, lat, lon, source, detail).
"""

from __future__ import annotations

import argparse
import json
import logging

import h3
import pandas as pd

from backend.layers._common import raw_path

from .build_grid import build_grid
from .region import region_ids
from .run import region_dir

log = logging.getLogger("groundwork.pois")
URLS = {
    "gppd.csv": "https://raw.githubusercontent.com/wri/global-power-plant-database/master/output_database/global_power_plant_database.csv",
    "airports.csv": "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv",
    "ne_ports.zip": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_ports.zip",
    "ne_lakes.zip": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip",
    "uk_stations.json": "https://raw.githubusercontent.com/davwheat/uk-railway-stations/main/stations.json",
    "peeringdb_fac.json": "https://www.peeringdb.com/api/fac?fields=id,name,latitude,longitude,country,city",
    "peeringdb_ixfac.json": "https://www.peeringdb.com/api/ixfac?fields=ix_id,fac_id",
}


def _file(name: str) -> str:
    path = raw_path("pois", name)
    if not path.exists() or path.stat().st_size < 1000:
        import requests

        resp = requests.get(URLS[name], timeout=300)
        resp.raise_for_status()  # e.g. PeeringDB throttles anonymous clients (HTTP 429)
        path.write_bytes(resp.content)
    return str(path)


def _row(kind: str, source: str, pid: str, name: str, lat: float, lon: float, detail: str = "") -> dict:
    return {"id": f"{source}:{pid}", "kind": kind, "name": str(name or kind.replace("_", " ")),
            "lat": round(float(lat), 6), "lon": round(float(lon), 6), "source": source, "detail": detail}


def collect() -> pd.DataFrame:
    rows: list[dict] = []
    for s in json.loads(open(_file("uk_stations.json"), encoding="utf-8").read()):
        rows.append(_row("station", "nr", s.get("crsCode") or s["stationName"], s["stationName"], s["lat"], s["long"]))
    gp = pd.read_csv(_file("gppd.csv"), usecols=["gppd_idnr", "name", "latitude", "longitude", "primary_fuel", "capacity_mw"])
    for r in gp.itertuples():
        rows.append(_row("power_plant", "gppd", r.gppd_idnr, r.name, r.latitude, r.longitude,
                         f"{r.primary_fuel}, {r.capacity_mw:g} MW"))
    ap = pd.read_csv(_file("airports.csv"), usecols=["ident", "type", "name", "latitude_deg", "longitude_deg", "iata_code"])
    for r in ap[ap["type"].isin(["large_airport", "medium_airport"])].itertuples():
        rows.append(_row("airport", "ourairports", r.ident, r.name, r.latitude_deg, r.longitude_deg,
                         f"{r.type.split('_')[0]}{', ' + r.iata_code if isinstance(r.iata_code, str) else ''}"))
    import shapefile

    for fname, kind, src in (("ne_ports.zip", "port", "ne_ports"), ("ne_lakes.zip", "water", "ne_lakes")):
        rd = shapefile.Reader(_file(fname))
        fields = [f[0] for f in rd.fields[1:]]
        for i, sr in enumerate(rd.iterShapeRecords()):
            rec = dict(zip(fields, sr.record, strict=False))
            name = rec.get("name") or rec.get("NAME")
            if kind == "water" and not name:
                continue
            if kind == "port" or not hasattr(sr.shape, "bbox"):
                lon, lat = sr.shape.points[0]
            else:
                x0, y0, x1, y1 = sr.shape.bbox
                lon, lat = (x0 + x1) / 2, (y0 + y1) / 2
            detail = str(rec.get("featurecla", "")).lower() if kind == "water" else ""
            rows.append(_row(kind, src, i, name, lat, lon, detail))
    facs = json.loads(open(_file("peeringdb_fac.json"), encoding="utf-8").read()).get("data", [])
    ix_facs = {r["fac_id"] for r in json.loads(open(_file("peeringdb_ixfac.json"), encoding="utf-8").read()).get("data", [])}
    for f in facs:
        if f.get("latitude") is None or f.get("longitude") is None:
            continue
        kind = "ixp" if f["id"] in ix_facs else "data_centre"
        rows.append(_row(kind, "peeringdb", f["id"], f["name"], f["latitude"], f["longitude"], f.get("city") or ""))
    df = pd.DataFrame(rows).dropna(subset=["lat", "lon"])
    return df[(df["lat"].abs() <= 90) & (df["lon"].abs() <= 180)]


def for_region(region: str, all_pois: pd.DataFrame) -> pd.DataFrame:
    grid = build_grid(region_id=region)
    res = grid.attrs["resolution"]
    w, s, e, n = grid.attrs["bbox"]
    cand = all_pois[(all_pois["lon"] >= w) & (all_pois["lon"] <= e) & (all_pois["lat"] >= s) & (all_pois["lat"] <= n)]
    cells = set(grid.index)
    keep = [h3.latlng_to_cell(la, lo, res) in cells for la, lo in zip(cand["lat"], cand["lon"], strict=True)]
    return cand[keep].reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", default="uk", help="region id or 'all'")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    allp = collect()
    for rid in region_ids() if args.region == "all" else [args.region]:
        out = region_dir(rid)
        out.mkdir(parents=True, exist_ok=True)
        df = for_region(rid, allp)
        df.to_parquet(out / "pois.parquet", index=False, compression="zstd")
        log.info("%s: %d POIs %s", rid, len(df), df["kind"].value_counts().to_dict())


if __name__ == "__main__":
    main()
