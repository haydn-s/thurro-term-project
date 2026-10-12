"""The wire contract: every endpoint, the probes, auth and the SSE path."""
import dataclasses

from fastapi.testclient import TestClient

from app import main
from app.service import SignalService


def test_health_is_open_and_does_not_touch_the_model(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready_reports_ready_with_a_good_panel(client):
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ready", "model_loaded": True,
        "feature_store_loaded": True, "detail": None,
    }


def test_ready_is_503_and_explains_itself_when_the_panel_is_missing(settings, tmp_path):
    broken = dataclasses.replace(settings, feature_store=tmp_path)
    main.service = SignalService(broken)
    main.settings = broken
    with TestClient(main.app) as test_client:
        response = test_client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert "FEATURE_STORE" in body["detail"]
    # Liveness must stay green: the process is fine, its inputs are not.
    with TestClient(main.app) as test_client:
        assert test_client.get("/health").status_code == 200


def test_signal_endpoints_are_503_when_unready(settings, tmp_path):
    broken = dataclasses.replace(settings, feature_store=tmp_path)
    main.service = SignalService(broken)
    main.settings = broken
    with TestClient(main.app) as test_client:
        assert test_client.get("/signals").status_code == 503


def test_metadata_carries_what_a_consumer_needs_to_integrate(client):
    body = client.get("/metadata").json()
    assert body["service"] == "ev-capex-signal"
    assert body["model"]["is_baseline"] is True
    assert body["model"]["artifact"] is None
    assert body["auth_required"] is False
    assert body["companies"], "metadata must list the scored symbols"
    assert {"path", "method", "summary"} <= set(body["endpoints"][0])


def test_signals_returns_a_described_cross_section(client):
    body = client.get("/signals").json()
    assert body["count"] == len(body["signals"]) > 0
    assert body["model"]["name"] == "capex-intensity-baseline"
    assert body["feature_store"]["rows"] > 0
    first = body["signals"][0]
    assert {"nse_symbol", "score", "direction", "confidence", "basis"} <= set(first)
    assert first["direction"] in {"expand", "replace", "contract"}
    assert 0.0 <= first["confidence"] <= 1.0


def test_tier_filter_narrows_without_changing_the_envelope(client):
    everything = client.get("/signals").json()
    tier = everything["signals"][0]["tier"]
    filtered = client.get("/signals", params={"tier": tier}).json()
    assert 0 < filtered["count"] <= everything["count"]
    assert {s["tier"] for s in filtered["signals"]} == {tier}
    assert filtered["model"] == everything["model"]


def test_direction_filter_rejects_a_value_outside_the_enum(client):
    assert client.get("/signals", params={"direction": "expand"}).status_code == 200
    assert client.get("/signals", params={"direction": "sideways"}).status_code == 422


def test_min_confidence_filter(client):
    strict = client.get("/signals", params={"min_confidence": 1.0}).json()
    assert all(s["confidence"] >= 1.0 for s in strict["signals"])
    assert client.get("/signals", params={"min_confidence": 2.0}).status_code == 422


def test_single_company_lookup_is_case_insensitive(client):
    symbol = client.get("/signals").json()["signals"][0]["nse_symbol"]
    upper = client.get(f"/signals/{symbol.upper()}")
    lower = client.get(f"/signals/{symbol.lower()}")
    assert upper.status_code == lower.status_code == 200
    assert upper.json() == lower.json()
    assert upper.json()["nse_symbol"] == symbol


def test_unknown_company_is_404_and_says_where_to_look(client):
    response = client.get("/signals/NOTREAL")
    assert response.status_code == 404
    assert "/metadata" in response.json()["detail"]


def test_refresh_is_not_mistaken_for_a_company_symbol(client):
    # Route order in main.py exists for this; a regression here would make
    # /signals/refresh resolve as the company "refresh" and 404.
    response = client.post("/signals/refresh")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "refreshed"
    assert body["signals"] > 0


def test_auth_gates_signals_but_never_the_probes(service, settings):
    secured = dataclasses.replace(settings, api_token="s3cret")
    main.service = service
    main.settings = secured
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200

        assert client.get("/signals").status_code == 401
        assert client.get("/metadata").status_code == 401
        assert client.get(
            "/signals", headers={"Authorization": "Bearer wrong"}
        ).status_code == 401
        assert client.get(
            "/signals", headers={"Authorization": "Basic s3cret"}
        ).status_code == 401
        assert client.get(
            "/signals", headers={"Authorization": "Bearer s3cret"}
        ).status_code == 200


def test_openapi_schema_is_generated(client):
    schema = client.get("/openapi.json").json()
    assert "/signals" in schema["paths"]
    assert "/stream" in schema["paths"]
