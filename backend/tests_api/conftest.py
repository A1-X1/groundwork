import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
# Tests run against the stub unless told otherwise (GROUNDWORK_SCORING=real make test-api).
os.environ.setdefault("GROUNDWORK_SCORING", "stub")

import tempfile  # noqa: E402

# Tests never touch the real app database.
os.environ["GROUNDWORK_DB"] = os.path.join(
    tempfile.mkdtemp(prefix="gw-test-"), "test.db"
)

from fastapi.testclient import TestClient  # noqa: E402

from backend.api.main import app, score_cache  # noqa: E402

CONTRACTS = ROOT / "shared" / "contracts"


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    score_cache.clear()


@pytest.fixture(scope="session")
def schema() -> dict:
    import json

    return json.loads((CONTRACTS / "score_response.schema.json").read_text())
