"""Distributed tracing: context propagation, internal spans, log correlation.

Spans are asserted against a real SDK provider with an in-memory exporter, not
mocked. The global tracer provider can only be set once per process, so it is
installed session-wide and the exporter is cleared between tests.
"""
import dataclasses
import json
import logging

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app import main
from app.config import Settings
from app.observability import JsonFormatter, current_trace_ids, request_id_var
from app.service import SignalService

#: A caller's trace, in W3C traceparent form: version-traceid-spanid-flags.
CALLER_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
CALLER_SPAN_ID = "00f067aa0ba902b7"
TRACEPARENT = f"00-{CALLER_TRACE_ID}-{CALLER_SPAN_ID}-01"


@pytest.fixture(scope="session")
def exporter():
    """Install a real SDK provider globally, once.

    `app.observability.tracer` and FastAPI's own tracer both resolve through
    the API's proxy provider, so they pick this up even though they were
    created at import time, before this existed.
    """
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    trace.set_tracer_provider(provider)
    return memory


@pytest.fixture()
def spans(exporter):
    exporter.clear()
    return exporter


def _names(spans):
    return [s.name for s in spans.get_finished_spans()]


def _by_name(spans, name):
    return next(s for s in spans.get_finished_spans() if s.name == name)


# -- context propagation ---------------------------------------------------

def test_a_callers_trace_is_continued_not_restarted(client, spans):
    """The whole point of distributed tracing.

    A consumer calling /signals as part of its own workflow must see this
    request inside its trace, not as a disconnected one of ours.
    """
    client.get("/signals", headers={"traceparent": TRACEPARENT})

    request_span = _by_name(spans, "GET /signals")
    assert f"{request_span.context.trace_id:032x}" == CALLER_TRACE_ID
    assert f"{request_span.parent.span_id:016x}" == CALLER_SPAN_ID


def test_a_request_without_a_traceparent_starts_its_own_trace(client, spans):
    client.get("/signals")
    request_span = _by_name(spans, "GET /signals")
    assert request_span.parent is None
    assert f"{request_span.context.trace_id:032x}" != CALLER_TRACE_ID


def test_every_span_in_one_request_shares_its_trace(client, spans):
    client.get("/signals", headers={"traceparent": TRACEPARENT})
    ids = {f"{s.context.trace_id:032x}" for s in spans.get_finished_spans()}
    assert ids == {CALLER_TRACE_ID}, "a request must not fragment into traces"


def test_operation_spans_break_the_request_down(client, spans):
    """Without these a trace is one flat span saying only "it took 3ms"."""
    client.get("/signals")
    names = _names(spans)
    for phase in ("fastapi.dependencies", "fastapi.endpoint",
                  "fastapi.serialization"):
        assert phase in names, f"{phase} span missing"


# -- probe exclusion -------------------------------------------------------

@pytest.mark.parametrize("path", ["/health", "/ready", "/metrics"])
def test_probes_and_scrapes_are_not_traced(client, spans, path):
    """A 10s healthcheck and a Prometheus scrape would swamp a backend.

    Their failures are already visible in metrics and logs, so the spans would
    be cost without information.
    """
    client.get(path)
    assert _names(spans) == [], f"{path} produced spans: {_names(spans)}"


def test_the_exclusion_predicate_covers_exactly_the_probes():
    from app.main import _exclude_from_traces
    assert _exclude_from_traces({"path": "/health"}) is True
    assert _exclude_from_traces({"path": "/ready"}) is True
    assert _exclude_from_traces({"path": "/metrics"}) is True
    assert _exclude_from_traces({"path": "/signals"}) is False
    assert _exclude_from_traces({}) is False


# -- our own spans ---------------------------------------------------------

def test_the_work_this_service_actually_does_is_instrumented(client, spans):
    """FastAPI cannot see inside a reload; these spans are what localise it.

    "The request was slow" and "parsing the panel was slow" need different
    fixes, so they need different spans.
    """
    client.post("/signals/refresh")
    names = _names(spans)
    assert "feature_store.load" in names
    assert "model.load" in names
    assert "model.signals" in names

    load = _by_name(spans, "feature_store.load")
    assert load.attributes["panel.rows"] > 100
    assert "panel_company_annual.csv" in load.attributes["panel.source"]

    scoring = _by_name(spans, "model.signals")
    assert scoring.attributes["model.name"] == "capex-intensity-baseline"
    assert scoring.attributes["signals.count"] > 0


def test_internal_spans_nest_under_the_request(client, spans):
    client.post("/signals/refresh", headers={"traceparent": TRACEPARENT})
    load = _by_name(spans, "feature_store.load")
    assert load.parent is not None, "a reload span must not be a root"
    assert f"{load.context.trace_id:032x}" == CALLER_TRACE_ID


def test_startup_is_one_trace_not_three_orphans(settings, spans):
    """Regression: the startup load produced three parentless single-span traces.

    At startup there is no request span, so feature_store.load, model.load and
    model.signals each became their own trace with no context. Three orphans in
    a backend say nothing; one tree says how long the container took to become
    useful and which part was slow.
    """
    with TestClient(main.app):
        pass

    startup = _by_name(spans, "service.startup")
    assert startup.parent is None, "startup is legitimately a root"
    children = [s for s in spans.get_finished_spans()
                if s.parent is not None
                and s.parent.span_id == startup.context.span_id]
    assert {c.name for c in children} == {
        "feature_store.load", "model.load", "model.signals"
    }
    assert startup.attributes["panel.rows"] > 100


# -- log correlation -------------------------------------------------------

def test_log_lines_carry_the_trace_they_happened_in(spans):
    """Correlation is the payoff: a log line pivots to its trace."""
    from app.observability import tracer

    with tracer.start_as_current_span("unit"):
        ids = current_trace_ids()
        assert ids is not None
        trace_id, span_id = ids

        record = logging.LogRecord(
            name="t", level=logging.INFO, pathname="x", lineno=1,
            msg="inside a span", args=(), exc_info=None,
        )
        payload = json.loads(JsonFormatter().format(record))

    assert payload["trace_id"] == trace_id
    assert payload["span_id"] == span_id
    assert len(trace_id) == 32 and len(span_id) == 16
    int(trace_id, 16), int(span_id, 16)  # must be hex


def test_no_trace_fields_when_there_is_no_span():
    """Absent, not present-and-zero. A zeroed id is a real id to a backend."""
    assert current_trace_ids() is None

    record = logging.LogRecord(
        name="t", level=logging.INFO, pathname="x", lineno=1,
        msg="outside any span", args=(), exc_info=None,
    )
    token = request_id_var.set("req-only")
    try:
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert "trace_id" not in payload
    assert "span_id" not in payload
    # The request id is the fallback handle when tracing is off.
    assert payload["request_id"] == "req-only"


# -- configuration ---------------------------------------------------------

def test_tracing_is_off_until_an_endpoint_is_configured(settings):
    assert settings.otel_endpoint is None
    assert settings.tracing_enabled is False


def test_tracing_is_on_once_an_endpoint_is_set(settings):
    live = dataclasses.replace(settings, otel_endpoint="http://collector:4318")
    assert live.tracing_enabled is True


def test_otel_sdk_disabled_overrides_a_configured_endpoint(settings):
    """The standard kill switch has to win, or it is not a kill switch."""
    off = dataclasses.replace(
        settings, otel_endpoint="http://collector:4318", otel_sdk_disabled=True
    )
    assert off.tracing_enabled is False


def test_the_traces_specific_endpoint_takes_precedence(monkeypatch):
    """Precedence the OTel spec defines, not one we chose."""
    monkeypatch.setenv("FEATURE_STORE", "../data/processed")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://general:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://traces:4318")
    assert Settings.from_env().otel_endpoint == "http://traces:4318"


def test_metadata_tells_a_consumer_whether_a_trace_exists(client):
    body = client.get("/metadata").json()
    assert body["tracing"] is False, "no endpoint configured in the test settings"


def test_metadata_reports_tracing_on_when_configured(service, settings):
    live = dataclasses.replace(settings, otel_endpoint="http://collector:4318")
    main.service, main.settings = SignalService(live), live
    with TestClient(main.app) as client:
        assert client.get("/metadata").json()["tracing"] is True
