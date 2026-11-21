"""Train and save feasibility models for every profile that declares one.

    python -m backend.scoring.train                 # all profiles with a model
    python -m backend.scoring.train data_centre     # just one
    python -m backend.scoring.train --offline       # use cached/seeded positives only

Models go to <data dir>/models/<profile>.txt with a <profile>.json sidecar (metrics,
features, grid fingerprint). The API retrains in memory if a saved model is stale.
"""

from __future__ import annotations

import argparse
import logging

from . import data as _data
from . import ml
from .profiles import load_profiles


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profiles", nargs="*", help="profile ids (default: all with a model)")
    ap.add_argument("--offline", action="store_true", help="do not download positives")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")

    grid = _data.load()
    profiles = load_profiles(set(grid.layer_ids))
    wanted = args.profiles or [p for p, prof in profiles.items() if prof.model]
    for pid in wanted:
        if pid not in profiles:
            raise SystemExit(f"unknown profile {pid!r}")
        if profiles[pid].model is None:
            print(f"{pid}: no model declared, skipping")
            continue
        model = ml.train(grid, profiles[pid], allow_network=not args.offline)
        path = ml.save(model, ml.model_dir(grid))
        m = model.metrics
        print(f"{pid}: {m['n_positives']} positives ({'synthetic/seeded' if m['positives_synthetic'] else 'real'}), "
              f"spatial-CV AUC {m['auc_spatial_cv']} → {path}")


if __name__ == "__main__":
    main()
