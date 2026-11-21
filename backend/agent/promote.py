"""Move an agent-made building from data/local/ (gitignored) into the repo so it can be committed.

    python -m backend.agent.promote theme_park          # profile + its generated layers + 3D model
    python -m backend.agent.promote theme_park --dry-run

Agent output is saved locally by default so a teammate's `git pull` never collides with files
your app created. Promote only the ones you want to share.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import yaml

from backend.layers import _common, _generic

from .models3d import MODELS_DIR, local_models_dir
from .tools import PROFILES_DIR, local_profiles_dir


def plan(profile_id: str) -> list[tuple[Path, Path]]:
    src = local_profiles_dir() / f"{profile_id}.yaml"
    if not src.exists():
        raise SystemExit(f"no local profile {profile_id!r} in {local_profiles_dir()}")
    moves = [(src, PROFILES_DIR / src.name)]
    doc = yaml.safe_load(src.read_text().split("\n", 1)[1] if src.read_text().startswith("#") else src.read_text())
    used = set(doc.get("layers", {})) | set(doc.get("masks", []))
    for lid in sorted(used):
        layer = _generic.local_dir() / f"{lid}.yaml"
        if layer.exists():
            moves.append((layer, _generic.GENERATED_DIR / layer.name))
    model = local_models_dir() / f"{profile_id}.json"
    if model.exists():
        moves.append((model, MODELS_DIR / model.name))
    return moves


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile_id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    for src, dst in plan(args.profile_id):
        rel = lambda p: p.relative_to(_common.REPO_ROOT) if p.is_relative_to(_common.REPO_ROOT) else p  # noqa: E731
        print(f"{'would move' if args.dry_run else 'moved'} {rel(src)} → {rel(dst)}")
        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), dst)
    if not args.dry_run:
        print("Now `git add` those files and commit. Rebuild the region grid with `make data` if new layers moved.")


if __name__ == "__main__":
    main()
