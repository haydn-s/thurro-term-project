"""The outlook: verifying the artifact at load, and the two endpoints that serve it."""
import dataclasses
import json
import math
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import main
from app.outlook import Outlook, OutlookArtifactError, add_months, month_closed
from app.service import SignalService


@pytest.fixture()
def outlook(settings) -> Outlook:
    return Outlook.load(settings.outlook_artifact)


@pytest.fixture()
def raw(settings) -> dict:
    """The committed artifact as plain JSON, for a test to corrupt."""
    return json.loads(settings.outlook_artifact.read_text())


def _write(tmp_path, raw: dict):
    path = tmp_path / "outlook.json"
    path.write_text(json.dumps(raw))
    return path


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


# -- the artifact ---------------------------------------------------------

def test_contributions_add_up_to_the_probability(outlook):
    # The property that makes `contributions` an explanation rather than a
    # decoration: intercept + contributions IS the logit being served.
    for model, row in [(outlook.national, outlook.national_row),
                       *[(outlook.state, r) for r in outlook.state_rows]]:
        total = model.intercept + math.fsum(c.contribution for c in row.contributions)
        assert total == pytest.approx(_logit(row.probability), abs=1e-9)


def test_contributions_come_largest_effect_first(outlook):
    sizes = [abs(c.contribution) for c in outlook.national_row.contributions]
    assert sizes == sorted(sizes, reverse=True)
    assert {c.feature for c in outlook.national_row.contributions} == set(outlook.national.features)


def test_states_are_ranked_highest_probability_first(outlook):
    probs = [r.probability for r in outlook.state_rows]
    assert probs == sorted(probs, reverse=True)
    assert len({r.state for r in outlook.state_rows}) == len(outlook.state_rows)


def test_a_changed_coefficient_is_refused(raw, tmp_path):
    # A hand-edited artifact would otherwise serve a number no model produced.
    raw["national"]["coefficients"][0] += 0.01
    with pytest.raises(OutlookArtifactError, match="recomputed probability"):
        Outlook.load(_write(tmp_path, raw))


def test_a_changed_feature_value_is_refused(raw, tmp_path):
    row = raw["state"]["scored"][0]
    row["features"]["share_total"] += 0.05
    with pytest.raises(OutlookArtifactError, match=row["state"]):
        Outlook.load(_write(tmp_path, raw))


def test_a_coefficient_vector_of_the_wrong_length_is_refused(raw, tmp_path):
    raw["state"]["coefficients"].pop()
    with pytest.raises(OutlookArtifactError, match="entries for"):
        Outlook.load(_write(tmp_path, raw))


def test_another_schema_version_is_refused_not_half_read(raw, tmp_path):
    raw["schema_version"] = 2
    with pytest.raises(OutlookArtifactError, match="schema_version"):
        Outlook.load(_write(tmp_path, raw))


def test_month_arithmetic_and_the_closed_flag():
    assert add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert add_months(date(2026, 9, 1), 1) == date(2026, 10, 1)
    assert month_closed(date(2026, 10, 1), today=date(2026, 10, 31)) is False
    assert month_closed(date(2026, 10, 1), today=date(2026, 11, 1)) is True


# -- the service ----------------------------------------------------------

def test_missing_artifact_leaves_the_service_unready_and_says_where(settings, tmp_path):
    broken = dataclasses.replace(settings, outlook_artifact=tmp_path / "absent.json")
    main.service = SignalService(broken)
    main.settings = broken
    with TestClient(main.app) as client:
        ready = client.get("/ready")
        assert ready.status_code == 503
        assert ready.json()["outlook_loaded"] is False
        assert "OUTLOOK_ARTIFACT" in ready.json()["detail"]
        assert client.get("/outlook/national").status_code == 503
        assert client.get("/health").status_code == 200


def test_a_rebuilt_artifact_is_picked_up_without_a_restart(settings, raw, tmp_path):
    path = _write(tmp_path, raw)
    svc = SignalService(dataclasses.replace(settings, outlook_artifact=path))
    assert svc.national_outlook().model.notes == raw["national"]["notes"]

    raw["national"]["notes"] = ["rebuilt"]
    path.write_text(json.dumps(raw))
    # Push the mtime forward so the change is visible even on a filesystem with
    # coarse timestamps.
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    assert svc.national_outlook().model.notes == ["rebuilt"]


def test_a_corrupt_rebuild_keeps_the_last_good_outlook_serving(settings, raw, tmp_path):
    path = _write(tmp_path, raw)
    svc = SignalService(dataclasses.replace(settings, outlook_artifact=path))
    before = svc.national_outlook().probability

    raw["national"]["intercept"] += 1.0
    path.write_text(json.dumps(raw))
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    assert svc.national_outlook().probability == before
    assert "recomputed probability" in (svc.load_error or "")


# -- the endpoints --------------------------------------------------------

def test_national_outlook_is_next_month_with_its_drivers(client, outlook):
    body = client.get("/outlook/national").json()
    assert body["probability"] == pytest.approx(outlook.national_row.probability)
    data_through = date.fromisoformat(body["data_through"])
    assert date.fromisoformat(body["forecast_month"]) == add_months(data_through, 1)
    assert isinstance(body["forecast_month_closed"], bool)
    assert {c["feature"] for c in body["contributions"]} == set(body["model"]["features"])
    assert body["model"]["evaluation"]["test_months"] > 0
    assert body["model"]["notes"], "the caveats must travel with the number"


def test_state_outlook_ranks_every_state_and_top_cuts_it(client):
    full = client.get("/outlook/states").json()
    assert full["count"] == len(full["states"]) > 5
    assert [s["rank"] for s in full["states"]] == list(range(1, full["count"] + 1))
    probs = [s["probability"] for s in full["states"]]
    assert probs == sorted(probs, reverse=True)

    top = client.get("/outlook/states", params={"top": 5}).json()
    assert top["count"] == 5
    assert top["states"] == full["states"][:5]

    assert client.get("/outlook/states", params={"top": 0}).status_code == 422
    assert client.get("/outlook/states", params={"top": 101}).status_code == 422


def test_outlook_is_behind_the_token(service, settings):
    secured = dataclasses.replace(settings, api_token="s3cret")
    main.service = service
    main.settings = secured
    with TestClient(main.app) as client:
        for path in ("/outlook/national", "/outlook/states"):
            assert client.get(path).status_code == 401
            assert client.get(
                path, headers={"Authorization": "Bearer s3cret"}
            ).status_code == 200


def test_metadata_and_refresh_describe_the_outlook(client):
    meta = client.get("/metadata").json()
    assert meta["outlook"]["national"]["name"] == "national-announcement-logit"
    assert meta["outlook"]["state"]["name"] == "state-siting-logit"
    assert set(meta["outlook"]["inputs"]) >= {"announcements_clean.csv"}
    paths = {e["path"] for e in meta["endpoints"]}
    assert {"/outlook/national", "/outlook/states"} <= paths

    refreshed = client.post("/signals/refresh").json()
    assert refreshed["outlook"]["national"] == meta["outlook"]["national"]
