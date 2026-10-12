"""Cache invalidation: the panel changing on disk, and a model's own TTL.

The service caches the cross-section. Two things can make that cache wrong, and
they need different answers:

  the panel changed   -> reload everything, because the inputs are different
  the model is timed  -> recompute the signals, because the clock moved

Neither used to happen without `POST /signals/refresh`.
"""
import dataclasses
import shutil
import time

import pytest

from app import service as service_module
from app.features import ANNUAL_PANEL
from app.model import CapexIntensityBaseline, RawSignal
from app.service import SignalService


@pytest.fixture()
def panel_copy(tmp_path, panel_dir):
    """A writable copy of the real panel, so a test can mutate it."""
    shutil.copy(panel_dir / ANNUAL_PANEL, tmp_path / ANNUAL_PANEL)
    return tmp_path


@pytest.fixture()
def mutable_settings(settings, panel_copy):
    return dataclasses.replace(settings, feature_store=panel_copy)


def _drop_last_row(panel_copy):
    path = panel_copy / ANNUAL_PANEL
    lines = path.read_text().splitlines(keepends=True)
    path.write_text("".join(lines[:-1]))


class TickingModel:
    """A model whose output depends on the clock, not only on the panel.

    This is the case the TTL exists for. Without one it would serve its first
    answer for the lifetime of the container.
    """

    name = "ticking"
    version = "0.0.1"
    description = "Counts how many times it has been asked."
    score_units = "call_count"
    required_features = ()

    def __init__(self, ttl: float | None) -> None:
        self.signal_ttl_s = ttl
        self.calls = 0

    def signals(self, store):
        self.calls += 1
        return [RawSignal(
            nse_symbol="TICK", company="Tick Ltd", tier="test",
            score=float(self.calls), score_units=self.score_units,
            direction="expand", confidence=1.0,
        )]


@pytest.fixture()
def ticking(monkeypatch):
    """Install a TickingModel in place of whatever load_model would return."""
    def install(ttl):
        model = TickingModel(ttl)
        monkeypatch.setattr(service_module, "load_model", lambda artifact: model)
        return model
    return install


# -- the panel changing on disk -------------------------------------------

def test_a_rebuilt_panel_is_picked_up_without_an_api_call(mutable_settings, panel_copy):
    svc = SignalService(mutable_settings)
    before = svc.store_info().rows

    _drop_last_row(panel_copy)

    # No refresh call, no restart -- just the next read.
    svc.signal_set()
    assert svc.store_info().rows == before - 1


def test_an_unchanged_panel_is_not_reloaded(mutable_settings):
    svc = SignalService(mutable_settings)
    first = svc.computed_at
    for _ in range(5):
        svc.signal_set()
    assert svc.computed_at == first, "an idle panel must not trigger work"


def test_watching_can_be_turned_off(mutable_settings, panel_copy):
    svc = SignalService(dataclasses.replace(mutable_settings,
                                            watch_feature_store=False))
    before = svc.store_info().rows
    _drop_last_row(panel_copy)
    svc.signal_set()
    assert svc.store_info().rows == before, "watching is off; nothing should reload"
    # The explicit path still works.
    svc.reload()
    assert svc.store_info().rows == before - 1


def test_a_container_that_started_unready_heals_when_the_panel_appears(
    settings, tmp_path, panel_dir
):
    """The point of not crash-looping: fix the mount and it recovers.

    A container whose volume was not attached yet starts unready. It should pick
    the panel up on the next request rather than needing an operator to restart
    it after fixing the mount.
    """
    svc = SignalService(dataclasses.replace(settings, feature_store=tmp_path))
    assert not svc.ready

    shutil.copy(panel_dir / ANNUAL_PANEL, tmp_path / ANNUAL_PANEL)

    svc.ensure_fresh()
    assert svc.ready, "the panel is there now; the service should have loaded it"
    assert svc.signal_count() > 0


def test_a_failed_load_is_not_retried_on_every_request(settings, tmp_path, monkeypatch):
    """Retrying a known-bad panel per request would turn a mistake into load.

    The fingerprint of the failed attempt is recorded, so the next attempt waits
    for the file to actually change.
    """
    svc = SignalService(dataclasses.replace(settings, feature_store=tmp_path))
    assert not svc.ready

    attempts = []
    original = svc.reload
    monkeypatch.setattr(svc, "reload", lambda: (attempts.append(1), original())[1])

    for _ in range(10):
        svc.ensure_fresh()
    assert attempts == [], "nothing changed on disk; there was nothing to retry"


# -- a model's own TTL -----------------------------------------------------

def test_a_model_with_no_ttl_is_never_recomputed(mutable_settings, ticking):
    model = ticking(None)
    svc = SignalService(mutable_settings)
    assert model.calls == 1  # the initial load

    for _ in range(5):
        svc.signal_set()
    assert model.calls == 1, "a panel-only model must not be recomputed on a timer"


def test_a_timed_model_is_recomputed_once_its_ttl_lapses(mutable_settings, ticking):
    model = ticking(0.05)
    svc = SignalService(mutable_settings)
    assert model.calls == 1

    svc.signal_set()
    assert model.calls == 1, "still inside the ttl"

    time.sleep(0.06)
    svc.signal_set()
    assert model.calls == 2, "ttl lapsed; the cross-section should be recomputed"

    # And the payload reflects the new computation, not the cached one.
    assert svc.signal_set().signals[0].score == 2.0


def test_a_ttl_recompute_does_not_re_read_the_panel(mutable_settings, ticking):
    """The cheap path: the clock moved, the inputs did not.

    Recomputing should not re-parse the CSV or re-load the artifact, which is
    why this is a separate branch from a full reload.
    """
    ticking(0.05)
    svc = SignalService(mutable_settings)
    loaded_at = svc.store.loaded_at

    time.sleep(0.06)
    svc.signal_set()
    assert svc.store.loaded_at == loaded_at, "the panel should not have been re-read"


def test_as_of_advances_with_a_recompute(mutable_settings, ticking):
    ticking(0.05)
    svc = SignalService(mutable_settings)
    first = svc.signal_set().as_of
    time.sleep(0.06)
    assert svc.signal_set().as_of > first


# -- the shipped model -----------------------------------------------------

def test_the_baseline_declares_no_ttl_and_that_is_correct(store):
    """Not an accident worth preserving silently -- an assertion about the model.

    Intensity is cumulative over a filed panel and reads no clock, so its output
    is a pure function of its input. If someone gives the baseline a time term,
    this test should fail and make them set a TTL.
    """
    model = CapexIntensityBaseline()
    assert model.signal_ttl_s is None
    first = model.signals(store)
    second = model.signals(store)
    assert [s.score for s in first] == [s.score for s in second]


# -- the endpoints that report state --------------------------------------

def test_metadata_does_not_report_a_panel_that_has_been_replaced(
    mutable_settings, panel_copy
):
    """Provenance has to be current or it is actively misleading.

    /metadata is what a consumer reads to learn what the signals came from.
    It used to answer from the cache and report a row count for a panel that
    had already been rebuilt.
    """
    from fastapi.testclient import TestClient

    from app import main

    main.service = SignalService(mutable_settings)
    main.settings = mutable_settings
    with TestClient(main.app) as client:
        before = client.get("/metadata").json()["feature_store"]["rows"]
        _drop_last_row(panel_copy)
        after = client.get("/metadata").json()["feature_store"]["rows"]
    assert after == before - 1


def test_readiness_probe_heals_a_container_whose_volume_arrived_late(
    settings, tmp_path, panel_dir
):
    """Self-healing has to work through the probe, not just the read path.

    A load balancer will never send /signals to a container it believes is
    unready, so if only /signals re-checked, an unready container could never
    become ready on its own.
    """
    from fastapi.testclient import TestClient

    from app import main

    broken = dataclasses.replace(settings, feature_store=tmp_path)
    main.service = SignalService(broken)
    main.settings = broken

    with TestClient(main.app) as client:
        assert client.get("/ready").status_code == 503

        shutil.copy(panel_dir / ANNUAL_PANEL, tmp_path / ANNUAL_PANEL)

        # No restart, no /signals request -- just the next probe.
        assert client.get("/ready").status_code == 200
        assert client.get("/signals").json()["count"] > 0
