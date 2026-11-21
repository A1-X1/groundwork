# Generated layers

YAML layer specs written by the planning agent (`backend/agent`) or by hand. Each one
is one layer built from a vetted template in `backend/layers/_generic.py`: no code is
generated or executed. Schema:

```yaml
id: seismic_activity          # unique layer id (snake_case)
label: Seismic activity
unit: events (M≥4, 30 yr, 100 km)
kind: aggregate               # raster | proximity | aggregate
description: ...
template: usgs_earthquakes    # osm_proximity | osm_share | openmeteo_daily | usgs_earthquakes
params: {min_magnitude: 4.0, years: 30, radius_km: 100}
added_by: agent               # agent | human
```

Delete a file to remove the layer, then rerun `make data`.
