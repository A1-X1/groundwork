"""Azure ML connection and training for feasibility models.

Connection settings (no secrets) live in ``data/processed/connections.json`` or env vars:
``AZURE_SUBSCRIPTION_ID``, ``AZURE_RESOURCE_GROUP``, ``AZUREML_WORKSPACE`` and optional
``AZUREML_COMPUTE`` (omit for serverless compute). Authentication uses
``DefaultAzureCredential``: ``az login`` on a laptop, a service principal
(``AZURE_CLIENT_ID``/``AZURE_TENANT_ID``/``AZURE_CLIENT_SECRET``) on a server, or the
interactive browser / device-code login that ``connect(..., interactive=True)`` starts.

Training exports the profile's training set locally, runs ``azure_job/train.py`` as an
Azure ML command job, downloads ``model.txt`` and installs it where the scoring library
loads it (with the grid fingerprint, so a stale model is never used).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from backend.scoring import data as _data
from backend.scoring import ml
from backend.scoring.profiles import Profile

JOB_DIR = Path(__file__).parent / "azure_job"
CONNECTIONS = _data.PROCESSED_DIR / "connections.json"
ENV_KEYS = {"subscription_id": "AZURE_SUBSCRIPTION_ID", "resource_group": "AZURE_RESOURCE_GROUP",
            "workspace": "AZUREML_WORKSPACE", "compute": "AZUREML_COMPUTE"}
REQUIRED = ("subscription_id", "resource_group", "workspace")
PORTAL_HINT = ("Create (or pick) an Azure Machine Learning workspace at https://ml.azure.com, then enter its "
               "subscription ID, resource group and workspace name under Connections → Azure ML and sign in.")


class AzureNotConnected(RuntimeError):
    """Raised when training needs Azure ML but no workspace is connected."""


_credential_override: Any = None


def set_credential(credential: Any) -> None:
    """Let the API hand over the credential its device-code sign-in produced."""
    global _credential_override
    _credential_override = credential


def _api_setting() -> dict[str, str]:
    """Workspace settings saved by the API's Connections screen (backend.api.db), if present."""
    try:
        from backend.api import db  # Person 2's module; optional

        return db.get_setting("azure_ml") or {}
    except Exception:  # noqa: BLE001 — API not installed or DB not initialised
        return {}


def config() -> dict[str, str]:
    """Env vars > API Connections settings > data/processed/connections.json."""
    saved = json.loads(CONNECTIONS.read_text()).get("azure_ml", {}) if CONNECTIONS.exists() else {}
    saved = {**saved, **{k: v for k, v in _api_setting().items() if v}}
    out = {k: os.environ.get(env) or saved.get(k, "") for k, env in ENV_KEYS.items()}
    return {k: v for k, v in out.items() if v}


def sdk_installed() -> bool:
    try:
        import azure.ai.ml  # noqa: F401
        import azure.identity  # noqa: F401
    except ImportError:
        return False
    return True


def status() -> dict[str, Any]:
    cfg = config()
    missing = [k for k in REQUIRED if k not in cfg]
    return {
        "configured": not missing,
        "missing": missing,
        "sdk_installed": sdk_installed(),
        "workspace": cfg.get("workspace"),
        "compute": cfg.get("compute") or "serverless",
        "how_to_connect": None if not missing else PORTAL_HINT,
    }


def _credential(interactive: bool = False) -> Any:
    from azure.identity import DefaultAzureCredential, DeviceCodeCredential, InteractiveBrowserCredential

    if _credential_override is not None:
        return _credential_override
    if not interactive:
        return DefaultAzureCredential(exclude_interactive_browser_credential=True)
    try:
        return InteractiveBrowserCredential()
    except Exception:  # noqa: BLE001 — headless: fall back to a device code
        return DeviceCodeCredential()


def client(interactive: bool = False) -> Any:
    if not sdk_installed():
        raise AzureNotConnected("Azure ML SDK not installed: uv pip install -r backend/agent/requirements.txt")
    cfg = config()
    missing = [k for k in REQUIRED if k not in cfg]
    if missing:
        raise AzureNotConnected(f"Azure ML not connected (missing {', '.join(missing)}). {PORTAL_HINT}")
    from azure.ai.ml import MLClient

    return MLClient(_credential(interactive), cfg["subscription_id"], cfg["resource_group"], cfg["workspace"])


def connect(subscription_id: str, resource_group: str, workspace: str, compute: str | None = None,
            interactive: bool = True) -> dict[str, Any]:
    """Save workspace settings (no secrets) and verify that we can sign in to them."""
    CONNECTIONS.parent.mkdir(parents=True, exist_ok=True)
    saved = json.loads(CONNECTIONS.read_text()) if CONNECTIONS.exists() else {}
    saved["azure_ml"] = {k: v for k, v in {"subscription_id": subscription_id, "resource_group": resource_group,
                                           "workspace": workspace, "compute": compute}.items() if v}
    CONNECTIONS.write_text(json.dumps(saved, indent=2) + "\n")
    ws = client(interactive).workspaces.get(workspace)
    return {"connected": True, "workspace": ws.name, "location": getattr(ws, "location", None)}


# ---- training data -----------------------------------------------------------
def export_training_set(grid: _data.GridData, profile: Profile, out_dir: Path) -> dict[str, Any]:
    """Write train.parquet + meta.json for azure_job/train.py."""
    import h3

    X, y, info = ml.training_set(grid, profile)
    features = ml.feature_columns(grid, profile)
    df = X[features].copy()
    df["label"] = y
    df["group"] = [h3.cell_to_parent(c, 5) for c in X.index]
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_dir / "train.parquet")
    meta = {"profile": profile.id, "features": features, "rounds": 150,
            "params": ml._params(info["n_positives"], info["n_background"]),
            "grid_fingerprint": grid.fingerprint(), **info}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def install_model(grid: _data.GridData, profile: Profile, job_out: Path, meta: dict[str, Any],
                  backend: str, job: str | None = None) -> Path:
    """Copy model.txt into <data dir>/models/ with the sidecar the scoring library checks."""
    models = ml.model_dir(grid)
    models.mkdir(parents=True, exist_ok=True)
    target = models / f"{profile.id}.txt"
    target.write_text((job_out / "model.txt").read_text())
    metrics = json.loads((job_out / "metrics.json").read_text())
    sidecar = {
        "auc_spatial_cv": metrics.get("auc_spatial_cv"), "n_positives": meta["n_positives"],
        "n_background": meta["n_background"], "positives_synthetic": meta["positives_synthetic"],
        "positives": profile.model.positives if profile.model else None,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "grid_fingerprint": meta["grid_fingerprint"], "features": meta["features"],
        "trained_on": backend, "azure_job": job,
    }
    (models / f"{profile.id}.json").write_text(json.dumps(sidecar, indent=2) + "\n")
    return target


def run_local(grid: _data.GridData, profile: Profile) -> dict[str, Any]:
    """Run the exact Azure job script in a subprocess (no Azure needed)."""
    work = _data.PROCESSED_DIR / "jobs" / profile.id
    meta = export_training_set(grid, profile, work / "data")
    subprocess.run([sys.executable, str(JOB_DIR / "train.py"), "--data", str(work / "data"),
                    "--out", str(work / "out")], check=True, capture_output=True, text=True)
    path = install_model(grid, profile, work / "out", meta, backend="local")
    return {"backend": "local", "model": str(path), **json.loads((work / "out" / "metrics.json").read_text())}


def submit(grid: _data.GridData, profile: Profile, wait: bool = True, timeout_s: int = 3600) -> dict[str, Any]:
    """Train in Azure ML. Raises AzureNotConnected if no workspace is set up."""
    from azure.ai.ml import Input, Output, command
    from azure.ai.ml.entities import Environment

    ml_client = client()
    work = _data.PROCESSED_DIR / "jobs" / profile.id
    meta = export_training_set(grid, profile, work / "data")
    env = Environment(name="groundwork-train", conda_file=str(JOB_DIR / "conda.yaml"),
                      image="mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu22.04:latest")
    job_kwargs: dict[str, Any] = {}
    compute = config().get("compute")
    if compute:
        job_kwargs["compute"] = compute
    else:  # serverless compute
        from azure.ai.ml.entities import ResourceConfiguration

        job_kwargs["resources"] = ResourceConfiguration(instance_type="Standard_DS3_v2", instance_count=1)
    job = command(
        code=str(JOB_DIR), command="python train.py --data ${{inputs.data}} --out ${{outputs.model}}",
        inputs={"data": Input(type="uri_folder", path=str(work / "data"))},
        outputs={"model": Output(type="uri_folder")},
        environment=env, display_name=f"groundwork-{profile.id}", experiment_name="groundwork-feasibility",
        **job_kwargs,
    )
    created = ml_client.jobs.create_or_update(job)
    result: dict[str, Any] = {"backend": "azure_ml", "job": created.name, "studio_url": created.studio_url,
                              "status": created.status}
    if not wait:
        return result
    deadline = time.time() + timeout_s
    while True:
        j = ml_client.jobs.get(created.name)
        if j.status in ("Completed", "Failed", "Canceled"):
            break
        if time.time() > deadline:
            return {**result, "status": j.status, "note": "still running; call wait_and_install later"}
        time.sleep(20)
    if j.status != "Completed":
        return {**result, "status": j.status}
    return {**result, **wait_and_install(grid, profile, created.name, meta)}


def wait_and_install(grid: _data.GridData, profile: Profile, job_name: str,
                     meta: dict[str, Any] | None = None) -> dict[str, Any]:
    ml_client = client()
    dl = _data.PROCESSED_DIR / "jobs" / profile.id / "azure_out"
    ml_client.jobs.download(job_name, download_path=str(dl), output_name="model")
    out = next(p.parent for p in dl.rglob("model.txt"))
    meta = meta or json.loads((_data.PROCESSED_DIR / "jobs" / profile.id / "data" / "meta.json").read_text())
    path = install_model(grid, profile, out, meta, backend="azure_ml", job=job_name)
    return {"status": "Completed", "model": str(path), **json.loads((out / "metrics.json").read_text())}
