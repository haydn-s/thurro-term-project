"""Metrics exposition, structured logs and request correlation."""
import dataclasses
import json
import logging

import pytest

from fastapi.testclient import TestClient

from app import main
from app.observability import (
    JsonFormatter,
    ObservabilityMiddleware,
    request_id_var,
    sse_connections,
)

#: Set by the fixture below so the gauge test can reach a built service without
#: taking one as an argument (it drives an async generator, not a request).
_SERVICE: list = []


@pytest.fixture(autouse=True)
def _expose_service(service):
    _SERVICE.clear()
    _SERVICE.append(service)
    yield
    _SERVICE.clear()


def test_metrics_exposes_our_series_in_prometheus_format(client):
    client.get("/signals")  # generate some traffic to measure
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text

    for series in (
        "signal_http_requests_total",
        "signal_http_request_duration_seconds",
        "signal_service_ready",
        "signal_set_size",
        "signal_feature_store_rows",
        "signal_model_info",
    ):
        assert series in body, f"{series} missing from /metrics"

    # The gauges must carry real values, not just be declared.
    assert "signal_service_ready 1.0" in body
    assert 'signal_model_info{' in body
    assert "capex-intensity-baseline" in body


def test_metrics_labels_by_route_template_not_raw_path(client):
    """Label cardinality is the thing that kills a scrape target.

    /signals/{nse_symbol} has 35 live values and unbounded junk ones from
    anything that probes the port. Each distinct label value is its own time
    series, so the template has to be the label.
    """
    client.get("/signals/M%26M")
    client.get("/signals/TVSMOTOR")
    client.get("/signals/NOTAREALSYMBOL")
    body = client.get("/metrics").text

    assert 'route="/signals/{nse_symbol}"' in body
    for leaked in ('route="/signals/M&M"', 'route="/signals/TVSMOTOR"',
                   'route="/signals/NOTAREALSYMBOL"'):
        assert leaked not in body, f"raw path leaked into a label: {leaked}"


def test_metrics_is_behind_the_token_when_auth_is_on(service, settings):
    secured = dataclasses.replace(settings, api_token="s3cret")
    main.service, main.settings = service, secured
    with TestClient(main.app) as client:
        assert client.get("/metrics").status_code == 401
        assert client.get(
            "/metrics", headers={"Authorization": "Bearer s3cret"}
        ).status_code == 200
        # The probes stay open; an orchestrator must not need the secret.
        assert client.get("/health").status_code == 200


def test_unmatched_paths_share_one_label(client):
    client.get("/no/such/path/1")
    client.get("/no/such/path/2")
    body = client.get("/metrics").text
    assert 'route="<unmatched>"' in body
    assert '/no/such/path/1' not in body


def test_request_id_is_generated_and_echoed(client):
    response = client.get("/health")
    request_id = response.headers.get("X-Request-ID")
    assert request_id and len(request_id) == 32


def test_inbound_request_id_is_honoured(client):
    response = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["X-Request-ID"] == "trace-abc-123"


def test_absurd_inbound_request_id_is_truncated(client):
    response = client.get("/health", headers={"X-Request-ID": "x" * 500})
    assert len(response.headers["X-Request-ID"]) == 128


def test_access_log_is_emitted_once_per_request_with_fields(client, caplog):
    with caplog.at_level(logging.INFO, logger="signal.access"):
        client.get("/signals")
    records = [r for r in caplog.records if r.name == "signal.access"]
    assert len(records) == 1, "exactly one access line per request"
    record = records[0]
    assert record.http_status == 200
    assert record.http_route == "/signals"
    assert record.http_method == "GET"
    assert record.duration_ms >= 0


def test_json_formatter_emits_one_parseable_object_per_line():
    record = logging.LogRecord(
        name="signal.access", level=logging.INFO, pathname="x", lineno=1,
        msg="GET %s %s", args=("/signals", 200), exc_info=None,
    )
    record.http_status = 200
    record.duration_ms = 1.25

    token = request_id_var.set("req-xyz")
    try:
        line = JsonFormatter().format(record)
    finally:
        request_id_var.reset(token)

    payload = json.loads(line)
    assert "\n" not in line, "a log line must not span lines"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "signal.access"
    assert payload["message"] == "GET /signals 200"
    assert payload["request_id"] == "req-xyz"
    # `extra=` fields land as real keys, not as text to regex out later.
    assert payload["http_status"] == 200
    assert payload["duration_ms"] == 1.25
    assert payload["ts"].endswith("Z")


def test_json_formatter_survives_an_unserialisable_extra():
    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname="x", lineno=1,
        msg="hi", args=(), exc_info=None,
    )
    record.weird = object()
    payload = json.loads(JsonFormatter().format(record))
    assert isinstance(payload["weird"], str)


def test_json_formatter_includes_tracebacks():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="t", level=logging.ERROR, pathname="x", lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(),
        )
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exception"]


def test_sse_connection_gauge_rises_and_returns_to_zero():
    """The gauge is decremented in a `finally`, so a dropped consumer cannot leak.

    Driven through the generator rather than through /stream: TestClient buffers
    a response until the app finishes, and /stream never does. The route itself
    is covered over a real socket by scripts/smoke_test.sh, which asserts the
    middleware is in the streaming path by checking for its X-Request-ID header.
    """
    import asyncio

    from app.main import signal_events
    from tests.test_stream import _take

    def gauge() -> float:
        return sse_connections._value.get()

    before = gauge()
    peak = []

    async def run():
        generator = signal_events(_SERVICE[0], 60.0)
        await anext(generator)
        peak.append(gauge())
        await generator.aclose()

    asyncio.run(asyncio.wait_for(run(), timeout=5.0))
    assert peak == [before + 1], "a live consumer must register on the gauge"
    assert gauge() == before, "the gauge must return to its prior value"


def test_middleware_ignores_non_http_scopes():
    """A lifespan or websocket scope must pass straight through."""
    seen = []

    async def downstream(scope, receive, send):
        seen.append(scope["type"])

    import asyncio
    middleware = ObservabilityMiddleware(downstream)
    asyncio.run(middleware({"type": "lifespan"}, None, None))
    assert seen == ["lifespan"]


def test_uvicorn_access_logger_is_silenced_so_requests_are_not_logged_twice():
    """Regression: this function runs after uvicorn configures logging.

    An earlier version set propagate=True on every uvicorn logger, which undid
    uvicorn's own `access_log=False` and logged every request twice -- once by
    uvicorn, once by the middleware. Only reproducible under a real uvicorn
    process, so it is pinned here at the logger level.
    """
    from app.observability import configure_logging

    access = logging.getLogger("uvicorn.access")
    access.propagate = True  # simulate uvicorn having set things up

    configure_logging("INFO", "json")

    assert access.propagate is False, "uvicorn's access log must stay off"
    assert not access.isEnabledFor(logging.INFO) or all(
        isinstance(h, logging.NullHandler) for h in access.handlers
    ), "nothing on uvicorn.access may reach a real handler"

    # Errors and startup messages must still flow through our formatter.
    assert logging.getLogger("uvicorn.error").propagate is True


def test_uvicorns_ansi_coloured_duplicate_message_is_dropped():
    """uvicorn puts a `color_message` on its records; it is noise in JSON."""
    record = logging.LogRecord(
        name="uvicorn.error", level=logging.INFO, pathname="x", lineno=1,
        msg="Started server process [%d]", args=(1,), exc_info=None,
    )
    record.color_message = "Started server process [\x1b[36m%d\x1b[0m]"
    payload = json.loads(JsonFormatter().format(record))
    assert "color_message" not in payload
    assert "\x1b" not in json.dumps(payload), "no ANSI escapes in a JSON log"
