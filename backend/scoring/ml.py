"""Presence-only feasibility models (LightGBM) with exact TreeSHAP explanations.

The model learns where things *have* been built, not where they *should* be. Its output is
a multiplier in [floor, 1] on the normative weighted score, never a score on its own.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .data import GridData
from .profiles import Profile

log = logging.getLogger("groundwork.scoring")
SEED = 7


@dataclass
class TrainedModel:
    profile_id: str
    booster: Any                 # lightgbm.Booster
    features: list[str]
    metrics: dict[str, Any]

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.booster.predict(frame[self.features].to_numpy(dtype=float)))

    def contributions(self, frame: pd.DataFrame) -> np.ndarray:
        """TreeSHAP values (log-odds), one column per feature plus the base value last."""
        return np.asarray(self.booster.predict(frame[self.features].to_numpy(dtype=float), pred_contrib=True))


def feature_columns(data: GridData, profile: Profile) -> list[str]:
    excluded = set(profile.model.exclude_features) if profile.model else set()
    return [lid for lid in data.layer_ids if lid not in excluded]


def training_set(data: GridData, profile: Profile, allow_network: bool = False) -> tuple[pd.DataFrame, np.ndarray, dict[str, Any]]:
    from backend.layers import positives

    assert profile.model is not None
    pos_cells, pos_synthetic = positives.resolve(profile.model.positives, data.frame, allow_network)
    pos = sorted(set(pos_cells) & set(data.frame.index))
    if len(pos) < 5:
        raise ValueError(f"{profile.id}: only {len(pos)} positive hexes; need at least 5")
    others = data.frame.index.difference(pos)
    rng = np.random.default_rng(SEED)
    n_bg = int(min(len(others), max(10 * len(pos), 300)))
    bg = sorted(rng.choice(others.to_numpy(), size=n_bg, replace=False).tolist())
    X = data.frame.loc[pos + bg]
    y = np.r_[np.ones(len(pos)), np.zeros(len(bg))]
    return X, y, {"n_positives": len(pos), "n_background": n_bg, "positives_synthetic": bool(pos_synthetic)}


def _params(n_pos: int, n_bg: int) -> dict[str, Any]:
    return {
        "objective": "binary", "learning_rate": 0.05, "num_leaves": 15,
        "min_data_in_leaf": max(3, n_pos // 5), "feature_fraction": 0.8,
        "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
        "scale_pos_weight": n_bg / max(n_pos, 1), "seed": SEED,
        "deterministic": True, "force_row_wise": True, "num_threads": 1, "verbose": -1,
    }


def spatial_cv_auc(X: pd.DataFrame, y: np.ndarray, features: list[str], params: dict[str, Any],
                   rounds: int) -> float | None:
    """Mean ROC AUC over folds grouped by H3 res-5 parent (blocks ~250 km²)."""
    import h3
    import lightgbm as lgb
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold

    groups = np.array([h3.cell_to_parent(c, 5) for c in X.index])
    n_splits = min(5, len(set(groups)))
    if n_splits < 2:
        return None
    aucs = []
    for tr, te in GroupKFold(n_splits=n_splits).split(X, y, groups):
        if len(set(y[tr])) < 2 or len(set(y[te])) < 2:
            continue
        b = lgb.train(params, lgb.Dataset(X.iloc[tr][features].to_numpy(dtype=float), y[tr]), rounds)
        aucs.append(roc_auc_score(y[te], b.predict(X.iloc[te][features].to_numpy(dtype=float))))
    return float(np.mean(aucs)) if aucs else None


def train(data: GridData, profile: Profile, rounds: int = 150, allow_network: bool = False) -> TrainedModel:
    import lightgbm as lgb

    X, y, info = training_set(data, profile, allow_network)
    features = feature_columns(data, profile)
    params = _params(info["n_positives"], info["n_background"])
    auc = spatial_cv_auc(X, y, features, params, rounds)
    booster = lgb.train(params, lgb.Dataset(X[features].to_numpy(dtype=float), y, feature_name=features), rounds)
    metrics = {
        **info,
        "auc_spatial_cv": None if auc is None else round(auc, 4),
        "positives": profile.model.positives if profile.model else None,
        "trained_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "grid_fingerprint": data.fingerprint(),
        "features": features,
    }
    log.info("trained %s: %d positives, spatial-CV AUC %s", profile.id, info["n_positives"], metrics["auc_spatial_cv"])
    return TrainedModel(profile.id, booster, features, metrics)


def save(model: TrainedModel, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{model.profile_id}.txt"
    model.booster.save_model(str(path))
    (directory / f"{model.profile_id}.json").write_text(json.dumps(model.metrics, indent=2) + "\n", encoding="utf-8")
    return path


def load_saved(data: GridData, profile: Profile, directory: Path) -> TrainedModel | None:
    """A saved model, if one exists and was trained on this exact grid and feature set."""
    import lightgbm as lgb

    path, meta_path = directory / f"{profile.id}.txt", directory / f"{profile.id}.json"
    if not path.exists() or not meta_path.exists():
        return None
    metrics = json.loads(meta_path.read_text(encoding="utf-8"))
    if metrics.get("grid_fingerprint") != data.fingerprint() or metrics.get("features") != feature_columns(data, profile):
        log.info("saved model for %s is stale; retraining in memory", profile.id)
        return None
    return TrainedModel(profile.id, lgb.Booster(model_file=str(path)), metrics["features"], metrics)


def model_dir(data: GridData) -> Path:
    return data.directory / "models"


def lightgbm_available() -> bool:
    """True if LightGBM imports. On macOS without libomp the import raises OSError
    ("Library not loaded: libomp.dylib"), not ImportError, so catch both."""
    try:
        import lightgbm  # noqa: F401
    except (ImportError, OSError):
        return False
    return True


def get_model(data: GridData, profile: Profile) -> TrainedModel | None:
    """Saved model if fresh, else trained in memory (~1 s). None if LightGBM is missing."""
    if profile.model is None:
        return None
    if not lightgbm_available():
        log.warning("lightgbm unavailable (not installed, or libomp missing on macOS): feasibility = 1.0 for %s",
                    profile.id)
        return None
    return load_saved(data, profile, model_dir(data)) or train(data, profile)


def feasibility(model: TrainedModel, data: GridData, floor: float) -> tuple[np.ndarray, np.ndarray]:
    """(probability, feasibility multiplier in [floor, 1] from the probability's regional rank)."""
    prob = model.predict(data.frame)
    ranks = pd.Series(prob).rank(method="average").to_numpy()
    pct = (ranks - 1) / max(len(prob) - 1, 1)
    return prob, floor + (1 - floor) * pct
