"""Pydantic response/request models. These drive the schemas shown at /docs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

H3_EXAMPLE = "88195da49bfffff"


class ErrorDetail(BaseModel):
    code: str = Field(description="Machine-readable error code.", examples=["not_found"])
    message: str = Field(description="Human-readable explanation.")
    detail: object | None = Field(default=None, description="Extra context, if any.")


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------- profiles & layers


class ProfileLayer(BaseModel):
    id: str = Field(description="Layer id.", examples=["crime_rate"])
    weight: float = Field(ge=0, description="Default weight (renormalised to sum to 1).")
    better: Literal["higher", "lower"] = Field(description="Which direction scores better.")


class Profile(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "house",
                "label": "House",
                "description": "Safe, connected, green and affordable places to live.",
                "layers": [
                    {"id": "crime_rate", "weight": 0.2, "better": "lower"},
                    {"id": "dist_station", "weight": 0.15, "better": "lower"},
                ],
                "masks": ["flood_zone_3", "protected_land"],
                "has_model": True,
            }
        }
    )

    id: str
    label: str
    description: str
    layers: list[ProfileLayer]
    masks: list[str] = Field(description="Layer ids used as hard no-go masks.")
    has_model: bool = Field(description="Whether an ML feasibility model multiplies the score.")
    is_default: bool = Field(
        default=False, description="Shown as a main option on the home screen (else under More)."
    )


class Layer(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "crime_rate",
                "label": "Crime rate",
                "unit": "per 1,000",
                "kind": "aggregate",
                "description": "Street-level crimes per 1,000 residents, last 12 months.",
                "source": "data.police.uk",
                "min": 21.4,
                "max": 412.9,
            }
        }
    )

    id: str
    label: str
    unit: str
    kind: Literal["raster", "proximity", "aggregate"]
    description: str
    source: str
    min: float = Field(description="Minimum raw value across the region.")
    max: float = Field(description="Maximum raw value across the region.")


class LayerValue(BaseModel):
    h3: str = Field(examples=[H3_EXAMPLE])
    value: float = Field(ge=0, le=1, description="Percentile-normalised value (0–1).")
    raw: float = Field(description="Value in the layer's original unit.")


class LayerValues(BaseModel):
    layer: str
    resolution: int
    cells: list[LayerValue]


# ---------------------------------------------------------------- scores (contract)


class ScoredCell(BaseModel):
    """One cell of `score_response.schema.json`."""

    model_config = ConfigDict(extra="forbid")

    h3: str = Field(pattern=r"^[0-9a-f]{15}$", examples=[H3_EXAMPLE])
    score: float | None = Field(
        ge=0, le=1, description="0–1 final score, or null when masked.", examples=[0.82]
    )
    masked: bool
    breakdown: dict[str, float] = Field(
        description=(
            "Signed contribution per layer relative to the regional mean "
            "(weight × (value − mean), direction-corrected)."
        ),
        examples=[{"crime_rate": 0.21, "dist_station": -0.05}],
    )


class ScoreResponse(BaseModel):
    """Frozen contract: `shared/contracts/score_response.schema.json`."""

    model_config = ConfigDict(extra="forbid")

    profile: str = Field(examples=["house"])
    resolution: int = Field(examples=[8])
    generated_at: datetime
    cells: list[ScoredCell]


class CustomScoreRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "profile": "data_centre",
                "weights": {"free_cooling_hours": 0.4, "dist_fibre_ix": 0.3},
                "bbox": [-0.2, 51.45, 0.0, 51.55],
            }
        }
    )

    profile: str = Field(description="Profile id to score.")
    weights: dict[str, float] = Field(
        default_factory=dict,
        description="Weight overrides keyed by layer id. Missing layers keep their default.",
    )
    bbox: tuple[float, float, float, float] | None = Field(
        default=None, description="Optional (min_lon, min_lat, max_lon, max_lat)."
    )


class ShapDriver(BaseModel):
    layer: str
    label: str
    value: float = Field(description="SHAP value (log-odds contribution to feasibility).")
    raw: float | None = Field(default=None, description="Raw layer value at this cell.")


class ShapExplanation(BaseModel):
    base_value: float
    positive: list[ShapDriver] = Field(description="Up to 5 drivers raising feasibility.")
    negative: list[ShapDriver] = Field(description="Up to 5 drivers lowering feasibility.")


class ModelInfo(BaseModel):
    type: str = Field(examples=["presence"])
    positives: str | None = Field(default=None, examples=["osm:telecom=data_center"])
    auc_spatial_cv: float | None = Field(default=None, description="Spatial block CV AUC.")
    n_positives: int | None = None
    positives_synthetic: bool | None = None
    note: str | None = None


class PointScore(BaseModel):
    profile: str
    h3: str = Field(examples=[H3_EXAMPLE])
    lat: float
    lon: float
    score: float | None
    masked: bool
    masks: list[str] = Field(default_factory=list, description="Mask layers hit at this cell.")
    sustainability: float | None = Field(default=None, description="Weighted layer score.")
    feasibility: float | None = Field(
        default=None, description="ML feasibility multiplier, if the profile has a model."
    )
    rank: int | None = Field(description="1 = best unmasked cell in the region.")
    ranked_cells: int = Field(description="Number of unmasked cells ranked.")
    percentile: float | None = Field(description="Share of ranked cells this cell beats (0–1).")
    weights: dict[str, float] = Field(default_factory=dict, description="Effective weights.")
    breakdown: dict[str, float]
    raw: dict[str, float] = Field(description="Raw layer values in original units.")
    shap: ShapExplanation | None = Field(
        default=None, description="Top SHAP drivers of the feasibility model."
    )
    model: ModelInfo | None = Field(default=None, description="Feasibility model metadata.")


class CompareEntry(BaseModel):
    profile: str
    label: str
    score: float | None
    masked: bool
    rank: int | None
    ranked_cells: int
    percentile: float | None


class CompareResponse(BaseModel):
    h3: str
    lat: float
    lon: float
    results: list[CompareEntry]


class Health(BaseModel):
    status: Literal["ok"]
    scoring_source: str = Field(description="`real` (backend.scoring) or `stub`.")
    data_generated_at: datetime | None = Field(description="When grid.parquet was built.")
    layers: dict[str, Literal["real", "synthetic", "unknown"]] = Field(
        description="Provenance of each layer."
    )
    real_layers: int
    synthetic_layers: int


class Region(BaseModel):
    id: str = Field(examples=["london"])
    name: str
    bbox: tuple[float, float, float, float] = Field(description="min_lon,min_lat,max_lon,max_lat")
    resolution: int
    cells: int
    is_sample: bool | None = None
    generated_at: str | None = None
