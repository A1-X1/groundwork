from __future__ import annotations

import sys
from pathlib import Path

import h3
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scoring.data import GridData  # noqa: E402
from backend.scoring.profiles import Profile  # noqa: E402
from backend.scoring.scorer import Scorer  # noqa: E402


@pytest.fixture
def tiny_grid() -> GridData:
    """Seven hexes (a centre + ring) with hand-set values for exact assertions."""
    centre = h3.latlng_to_cell(51.5074, -0.1278, 8)
    cells = [centre, *sorted(h3.grid_ring(centre, 1))]
    a = np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 0.5])
    b = np.array([1.0, 0.0, 0.5, 0.5, 0.5, 0.5, 0.5])
    mask = np.array([0, 0, 0, 0, 0, 0, 1.0])
    frame = pd.DataFrame({"a": a, "b": b, "m": mask, "raw_a": a * 100, "raw_b": b * 10, "raw_m": mask},
                         index=pd.Index(cells, name="h3"))
    frame["lat"] = [h3.cell_to_latlng(c)[0] for c in cells]
    frame["lon"] = [h3.cell_to_latlng(c)[1] for c in cells]
    layers = [{"id": i, "label": i.upper(), "unit": "u", "kind": "raster", "description": "", "source": "test",
               "min": 0.0, "max": 1.0} for i in ("a", "b", "m")]
    return GridData(directory=ROOT / "nonexistent", frame=frame, layers=layers, build={"resolution": 8})


@pytest.fixture
def tiny_scorer(tiny_grid: GridData) -> Scorer:
    profile = Profile.model_validate({
        "id": "t", "label": "T", "description": "test",
        "layers": {"a": {"weight": 3, "better": "lower"}, "b": {"weight": 1, "better": "higher"}},
        "masks": ["m"],
    })
    return Scorer(tiny_grid, {"t": profile})
