"""Feasibility-model training job. Runs unchanged in Azure ML or locally.

Input: a parquet with feature columns, ``label`` (1 = existing example, 0 = background)
and ``group`` (H3 res-5 parent for spatial block CV), plus ``meta.json`` (features,
params). Output: ``model.txt`` (LightGBM) and ``metrics.json``.
Only needs pandas, pyarrow, numpy, scikit-learn and lightgbm.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="folder with train.parquet and meta.json")
    ap.add_argument("--out", required=True, help="output folder")
    args = ap.parse_args(argv)
    data, out = Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    meta = json.loads((data / "meta.json").read_text())
    df = pd.read_parquet(data / "train.parquet")
    features, params, rounds = meta["features"], meta["params"], int(meta.get("rounds", 150))
    X, y, groups = df[features].to_numpy(dtype=float), df["label"].to_numpy(), df["group"].to_numpy()

    aucs = []
    n_splits = min(5, len(set(groups)))
    if n_splits >= 2:
        for tr, te in GroupKFold(n_splits=n_splits).split(X, y, groups):
            if len(set(y[tr])) < 2 or len(set(y[te])) < 2:
                continue
            b = lgb.train(params, lgb.Dataset(X[tr], y[tr]), rounds)
            aucs.append(roc_auc_score(y[te], b.predict(X[te])))
    booster = lgb.train(params, lgb.Dataset(X, y, feature_name=features), rounds)
    booster.save_model(str(out / "model.txt"))
    metrics = {"auc_spatial_cv": round(float(np.mean(aucs)), 4) if aucs else None,
               "n_rows": int(len(df)), "n_positives": int(y.sum()), "folds_scored": len(aucs)}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
