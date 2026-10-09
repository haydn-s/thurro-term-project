"""Shared fixtures.

app.config reads the environment at import time, so FEATURE_STORE has to be set
before anything under app/ is imported -- hence the module-level assignment here
rather than a fixture. conftest is imported before the test modules that import
app, which is the only ordering that works.
"""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Point the service at the repo's real panel. Testing against the committed data
# rather than a synthetic file is deliberate: it catches a schema change in
# build_panel.py breaking the service, which a fixture CSV would hide.
os.environ.setdefault("FEATURE_STORE", str(REPO_ROOT / "data" / "processed"))

import pytest  # noqa: E402

from app.config import Settings  # noqa: E402
from app.features import FeatureStore  # noqa: E402
from app.service import SignalService  # noqa: E402


@pytest.fixture(scope="session")
def panel_dir() -> Path:
    return REPO_ROOT / "data" / "processed"


@pytest.fixture(scope="session")
def store(panel_dir: Path) -> FeatureStore:
    return FeatureStore.load(panel_dir)


@pytest.fixture()
def settings(panel_dir: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8000,
        feature_store=panel_dir,
        model_artifact=None,
        signal_horizon="FY27",
        stream_interval_s=1.0,
        api_token=None,
        log_level="WARNING",
        cors_origins=(),
    )


@pytest.fixture()
def service(settings: Settings) -> SignalService:
    return SignalService(settings)
