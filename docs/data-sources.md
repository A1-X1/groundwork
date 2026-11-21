# Data sources

Every layer caches raw downloads in `data/raw/` and has a deterministic synthetic fallback, so a build never fails. `data/processed/build.json` (and `/health`) records which layers ended up **real** and which **synthetic**, and why.

Retrieval date: whenever you run `make data`. The weather and air-quality year is set in `backend/layers/_openmeteo.py` (`YEAR = 2025`).

## Endpoint status (tested 2026-11-21 from the cloud dev container)

| Endpoint | Key? | Status | Used for |
|---|---|---|---|
| `api.open-meteo.com/v1/elevation` | no | ✅ 200 | elevation, slope |
| `archive-api.open-meteo.com/v1/archive` | no | ✅ 200 (one 429 seen: daily per-IP limit on a shared cloud IP; fine from a laptop, and everything is cached) | temperature, humidity, wind, solar, wet bulb, free cooling, 10-year normals (precipitation, soil moisture, evapotranspiration, warming trend) |
| `air-quality-api.open-meteo.com` | no | ✅ 200 | NO₂, PM2.5 |
| `geocoding-api.open-meteo.com` | no | ✅ 200 | city lookup for `PAN_CITY` |
| `nominatim.openstreetmap.org` | no (≤ 1 req/s, real User-Agent) | ✅ 200 | country / city geocoding |
| `overpass-api.de` | no | ⚠️ refuses the cloud egress; mirrors used | OSM layers |
| `overpass.kumi.systems` (mirror) | no | ✅ 200 | OSM layers (automatic fallback) |
| `api.carbonintensity.org.uk` | no | ✅ 200 | grid carbon (GB) |
| `data.police.uk/api` | no | ✅ 200 | crime (England & Wales) |
| `www.planning.data.gov.uk/entity.geojson` | no | ✅ 200 | flood zones, Green Belt, SSSI (England) |
| `hub.worldpop.org/rest` | no | ✅ 200 | global population (next step) |
| `earthquake.usgs.gov/fdsnws` | no | ✅ 200 | global seismic hazard (next step) |
| `naciscdn.org` (Natural Earth) | no | ✅ 200 | country boundaries for the globe and `PAN_COUNTRY` |
| `www.geoboundaries.org/api` | no | ✅ 200 | admin boundaries worldwide |
| `raw.githubusercontent.com/owid/energy-data` | no | ✅ 200 | electricity carbon intensity per country |
| `copernicus-dem-30m.s3.amazonaws.com` | no | ✅ 200 | 30 m DEM tiles worldwide |
| `gibs.earthdata.nasa.gov` (WMTS) | no | ✅ 200 | Blue Marble globe imagery |
| `www.nomisweb.co.uk/api` | no | ✅ 200 | UK census population |
| `api.protectedplanet.net` | **yes, free** | 🔑 401 without token | worldwide protected areas (WDPA) |

### Sign-ups needed

1. **Protected Planet API token** (free): request at https://api.protectedplanet.net/request. Without it, protected land outside England falls back to OSM nature reserves.
2. **Mistral API key** for the voice assistant: https://console.mistral.ai (free experiment tier). It belongs in the API's `.env`.
3. *Optional, visuals only:* a **Google Maps Platform key** with the Map Tiles API (Photorealistic 3D Tiles) for a photoreal globe, or a free **Cesium ion** token. Neither is needed for data: every data layer has a free, keyless source above (Google's Air Quality / Solar APIs are not required).

### Refresh policy

The API never calls data sources at request time; it only reads `grid.parquet`. Downloads happen in `make data` and are cached in `data/raw/`:

| Data | Cache lifetime |
|---|---|
| Historical climate and air quality (fixed year, 10-year normals), elevation | forever (the period never changes) |
| OSM features, planning.data.gov.uk polygons | 30 days |
| Grid carbon intensity | 1 day |
| Police crime | per month of data |

`python -m backend.pipeline.run --refresh` forces a re-download; a failed refresh falls back to the cached copy. To keep data current, run `make data` once a day (cron or a scheduled job): unchanged sources cost no API calls.

## Automatic downloads (no key)

| Layers | Source | Licence | Notes |
|---|---|---|---|
| `elevation` (→ `slope`) | [Open-Meteo Elevation API](https://open-meteo.com/en/docs/elevation-api) (Copernicus GLO-90 DEM) | CC BY 4.0 (Open-Meteo); Copernicus DEM © DLR/Airbus, free licence | One value per hex centre, 100 per request. `slope` is the steepest gradient to a neighbouring hex. |
| `mean_temp_annual`, `summer_max_temp`, `wet_bulb_p99`, `free_cooling_hours`, `humidity_mean`, `wind_speed_mean`, `solar_irradiance` | [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) (ERA5 / ERA5-Land) | CC BY 4.0; ERA5 © ECMWF / Copernicus C3S | Hourly 2025 data on a 6×5 lattice, IDW-interpolated. Temperatures are lapse-rate corrected (6.5 °C/km) with the hex elevation. Wet bulb uses Stull (2011). Reanalysis is about 9 km, so the urban heat island is under-represented. |
| `air_quality_no2`, `air_quality_pm25` | [Open-Meteo Air Quality API](https://open-meteo.com/en/docs/air-quality-api) (CAMS Europe) | CC BY 4.0; CAMS © ECMWF | Annual mean of hourly values, same lattice. About 10 km resolution: misses roadside peaks. |
| `grid_carbon_intensity` | [National Grid ESO Carbon Intensity API](https://carbon-intensity.github.io/api-definitions/) | CC BY 4.0 | Mean 48 h forecast for region 13 (London). **Uniform across London**; only useful for multi-region areas. |
| `crime_rate` | [data.police.uk API](https://data.police.uk/docs/) | OGL v3 | Latest month by H3 res-6 polygon (split until under the 10k cap), annualised. Bulk CSVs are better (below). |
| `dist_station`, `dist_substation`, `dist_hv_line`, `dist_water_body`, `green_space_access`, `dist_major_road`, `land_use_residential`; ML positives for `data_centre` | [OpenStreetMap](https://www.openstreetmap.org/) via [Overpass API](https://overpass-api.de/) | ODbL 1.0, © OpenStreetMap contributors | Bbox around London padded by 3 km. Substations are filtered to ≥ 132 kV where tagged. |
| `flood_risk`, `flood_zone_3` | [EA Flood Map for Planning](https://www.data.gov.uk/dataset/flood-map-for-planning-rivers-and-sea-flood-zone-3) via [planning.data.gov.uk](https://www.planning.data.gov.uk/dataset/flood-risk-zone) | OGL v3 | Share of 7 sample points per hex inside Zone 3 (×1) or Zone 2 (×0.5). Zones ignore defences. |
| `protected_land` | planning.data.gov.uk `green-belt`, `site-of-special-scientific-interest`; OSM nature reserves / protected areas | OGL v3; ODbL | 1 if at least half the hex is covered. |
| `dist_fibre_ix` | Seeded list in `backend/layers/_places.py` | n/a | Public LINX/LONAP host sites, about 100 m accuracy. |

## Manual downloads (bulk files; free, no account)

Put these under `data/raw/`; the layer is synthetic until they exist.

| File | Layers | Source | Licence |
|---|---|---|---|
| `ons/lsoa_pwc.csv` | population, deprivation | ONS Open Geography Portal: *LSOA (Dec 2021) Population Weighted Centroids* (CSV) | OGL v3 |
| `ons/lsoa_population.csv` | `population_density` (→ `crime_rate` denominator) | [Nomis](https://www.nomisweb.co.uk/) Census 2021 **TS001** by LSOA 2021 | OGL v3 |
| `ons/imd.csv` | `deprivation_index` | [English Indices of Deprivation](https://www.gov.uk/government/collections/english-indices-of-deprivation), File 7 (scores). Use the edition whose LSOA vintage matches the centroid file. | OGL v3 |
| `landreg/pp-YYYY.csv` | `median_house_price` | [HM Land Registry Price Paid Data](https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads) (yearly files) | OGL v3 (see HMLR terms) |
| `onspd/postcodes.csv` (`pcds,lat,long`) | `median_house_price` | ONS Postcode Directory, trimmed to those three columns | OGL v3 + Royal Mail / OS terms |
| `gias/edubasealldata.csv` | `dist_primary_school`, `dist_secondary_school`, `school_quality_nearby` | [Get Information About Schools](https://get-information-schools.service.gov.uk/Downloads), *All establishment data* | OGL v3 |
| `police/YYYY-MM/*-street.csv` | `crime_rate` (12 months) | [data.police.uk bulk download](https://data.police.uk/data/): Metropolitan + City of London, street crime | OGL v3 |
| `planning/<dataset>.geojson` | flood, protected land | Full dataset GeoJSON from planning.data.gov.uk, if the API is slow | OGL v3 |
| `london_boundary.geojson` | grid | Official Greater London boundary (ONS / London Datastore), WGS84 | OGL v3 |

Without GIAS, schools fall back to OSM `amenity=school` (phase guessed from the name) and `school_quality_nearby` stays synthetic.

## Processing

- **Grid**: H3 res 8 (about 0.66 km² at London's latitude). The built-in outline is simplified: about 10% larger than the real 1,572 km², giving 2,654 hexes.
- **Normalisation**: percentile rank within the region, 0 = lowest, 1 = highest, ties averaged. Binary masks and shares (`flood_zone_3`, `protected_land`, `flood_risk`, `land_use_residential`) are stored as-is.
- **Gaps**: NaNs are filled from neighbouring hexes (1–3 rings), then the regional median. The share filled is recorded in `build.json`.
- **Synthetic fallbacks**: seeded by layer id (CRC32), London-shaped: heat island, Thames floodplain, hills (Hampstead, Crystal Palace, North Downs), east/west gradients. Plausible, not measured.

## ML positives

| Profile | Positives | Fallback |
|---|---|---|
| `data_centre` | OSM `telecom=data_center` / `building=data_center` | Seeded cluster list (`_places.DATA_CENTRES`) |
| `house` | Hexes with ≥ 50% `land_use_residential` | Synthetic when that layer is synthetic |

Positives are read from cache only at API time. `python -m backend.scoring.train` is the step that may download them.

## Limitations and ethics

- The presence model reflects past decisions (where things were built), not suitability. It can only scale a score down to `floor` (default 0.5).
- Crime is *recorded* crime per resident, which over-weights busy centres and reflects policing patterns. Deprivation and prices are proxies that can encode bias. Use them with care and keep them visible in breakdowns.
- Reanalysis climate and CAMS air quality are coarse.
- This is a decision-support demo, not planning advice.
