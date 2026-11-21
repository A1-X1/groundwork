"""Raw layer values → 0–1 (higher = more of the thing)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def percentile_rank(values: pd.Series) -> pd.Series:
    """Rank-based 0–1 scaling: min → 0, max → 1, ties share the average rank."""
    v = values.astype(float)
    n = v.notna().sum()
    if n <= 1 or v.nunique(dropna=True) <= 1:
        return pd.Series(np.where(v.notna(), 0.5, np.nan), index=v.index)
    return (v.rank(method="average") - 1) / (n - 1)


def normalise(values: pd.Series, method: str) -> pd.Series:
    if method == "identity":
        return values.astype(float).clip(0, 1)
    if method == "rank":
        return percentile_rank(values)
    raise ValueError(f"unknown normalisation {method!r}")
