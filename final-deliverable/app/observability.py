"""Metrics and structured logging.

Two things a container needs before anyone can debug it without sitting next to
it: a scrapeable `/metrics` endpoint and log lines a machine can parse.

Both are wired in by one pure-ASGI middleware. `BaseHTTPMiddleware` would have
been shorter but it wraps the response body, which is exactly wrong for
`/stream` -- the SSE path has to pass through untouched. This middleware only
observes `http.response.start` and leaves the body stream alone.
"""
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)
from starlette.datastructures import MutableHeaders

#: The current request's id, so any log line emitted while handling it carries
#: the id without every call site having to thread it through.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

#: Header the id is read from and echoed back on. Honouring an inbound value
#: means a trace started by a caller or an ingress survives into these logs.
REQUEST_ID_HEADER = "x-request-id"

PREFIX = "signal"

# -- metrics ---------------------------------------------------------------
# Every series is labelled by the matched ROUTE TEMPLATE, never the raw path.
# /signals/{nse_symbol} has 35 live values and unbounded junk ones from any
# scanner that finds the port; labelling by raw path would turn each into its
# own time series and eventually take the scrape target down.

http_requests = Counter(
    f"{PREFIX}_http_requests_total",
    "HTTP requests by method, matched route and status code.",
    ["method", "route", "status"],
)
http_duration = Histogram(
    f"{PREFIX}_http_request_duration_seconds",
    "Wall-clock time to serve a request, by method and matched route.",
    ["method", "route"],
    # Tuned to this service: a cached cross-section answers in single-digit
    # milliseconds, so the default buckets would put almost everything in the
    # first one and show nothing. The long tail is for /stream, which is held
    # open for as long as the consumer wants it.
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0, 5.0, 60.0, float("inf")),
)
sse_connections = Gauge(
    f"{PREFIX}_sse_connections_active",
    "SSE consumers currently connected to /stream.",
)
sse_events = Counter(
    f"{PREFIX}_sse_events_total",
    "SSE events pushed, by event type.",
    ["event"],
)
model_reloads = Counter(
    f"{PREFIX}_model_reloads_total",
    "Attempts to load the panel and model, by outcome.",
    ["result"],
)
signal_recomputes = Counter(
    f"{PREFIX}_recomputes_total",
    "Recomputations of the cross-section, by what triggered them.",
    ["reason"],
)
# State gauges. Set from the service at scrape time rather than on a timer --
# see `set_service_state`.
service_ready = Gauge(f"{PREFIX}_service_ready", "1 when panel and model are loaded, else 0.")
signal_set_size = Gauge(f"{PREFIX}_set_size", "Companies in the current cross-section.")
signal_set_age = Gauge(
    f"{PREFIX}_set_computed_timestamp_seconds",
    "Unix time the current cross-section was computed. Subtract from now() to "
    "alert on staleness.",
)
feature_store_rows = Gauge(f"{PREFIX}_feature_store_rows", "Rows in the loaded panel.")
feature_store_mtime = Gauge(
    f"{PREFIX}_feature_store_mtime_seconds",
    "Unix mtime of the loaded panel file.",
)
model_info = Info(f"{PREFIX}_model", "Identity of the model currently being served.")


def set_service_state(service) -> None:
    """Refresh the state gauges from the live service.

    Called by the /metrics handler rather than from a background task: these are
    cheap reads of already-loaded state, and a pull-time refresh cannot drift
    from what the service would actually answer with.
    """
    service_ready.set(1 if service.ready else 0)
    if not service.ready:
        return
    signal_set_size.set(service.signal_count())
    if service.computed_at is not None:
        signal_set_age.set(service.computed_at.timestamp())
    store = service.store
    if store is not None:
        feature_store_rows.set(len(store.rows))
        if store.source_mtime is not None:
            feature_store_mtime.set(store.source_mtime.timestamp())
    model = service.model
    if model is not None:
        model_info.info({
            "name": model.name,
            "version": model.version,
            "is_baseline": str(service.settings.model_artifact is None).lower(),
            "score_units": model.score_units,
        })


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


# -- logging ---------------------------------------------------------------

#: LogRecord attributes that are always present. Anything else on a record came
#: from an `extra=` and belongs in the JSON output.
_STANDARD_RECORD_FIELDS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()
) | {
    "message",
    "asctime",
    "taskName",
    # uvicorn attaches an ANSI-coloured copy of its own message. Useful on a
    # terminal, pure noise in a JSON field a log aggregator has to store.
    "color_message",
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for a log aggregator to index.

    Anything passed as `extra=` lands as a top-level key, so an access log line
    carries its status and duration as real fields rather than as text someone
    has to regex out later.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        for key, value in vars(record).items():
            if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # default=str so an unexpected object in `extra=` degrades to its repr
        # instead of raising inside the logging call and losing the line.
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable, with the request id appended when there is one."""

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        request_id = request_id_var.get()
        return f"{line}  [{request_id}]" if request_id else line


def configure_logging(level: str, fmt: str) -> None:
    """Install the root handler. Idempotent, so tests can call it repeatedly."""
    formatter: logging.Formatter
    if fmt == "json":
        formatter = JsonFormatter()
    else:
        formatter = TextFormatter("%(asctime)s %(levelname)-8s %(name)s %(message)s")

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, level, logging.INFO))

    # uvicorn ships its own handlers; drop them so its startup and shutdown
    # messages go through the formatter above and the stream stays uniform.
    for name in ("uvicorn", "uvicorn.error"):
        uv = logging.getLogger(name)
        uv.handlers.clear()
        uv.propagate = True

    # uvicorn.access is silenced here, not merely detached.
    #
    # This function runs when app.main is imported, which uvicorn does *after*
    # it has configured logging -- so anything this loop re-enables outlives
    # uvicorn's own `access_log=False`. Setting propagate=True on this logger
    # (as an earlier version did) resurrected the access log uvicorn had just
    # turned off, and every request was logged twice: once by uvicorn and once
    # by ObservabilityMiddleware.
    #
    # The middleware is the access log. It reports the same request with the
    # duration, the matched route and the request id attached, so uvicorn's
    # version is strictly redundant.
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.addHandler(logging.NullHandler())
    access.propagate = False


# -- middleware ------------------------------------------------------------

access_log = logging.getLogger("signal.access")


class ObservabilityMiddleware:
    """Times every request, records metrics, emits one access log line.

    Pure ASGI on purpose. `BaseHTTPMiddleware` buffers the response body through
    an anyio stream, which would sit between `/stream` and its consumer; this
    only inspects the response-start message and injects a header.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _inbound_request_id(scope) or uuid.uuid4().hex
        token = request_id_var.set(request_id)

        started = time.perf_counter()
        status = 500  # what gets recorded if the app raises before responding

        async def send_wrapper(message: dict) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - started
            method = scope.get("method", "-")
            # Set during routing, so it is only available now, on the way out.
            route = getattr(scope.get("route"), "path", None) or "<unmatched>"
            http_requests.labels(method, route, str(status)).inc()
            http_duration.labels(method, route).observe(duration)
            access_log.info(
                "%s %s %s %.1fms",
                method, scope.get("path", "-"), status, duration * 1000,
                extra={
                    "http_method": method,
                    "http_path": scope.get("path"),
                    "http_route": route,
                    "http_status": status,
                    "duration_ms": round(duration * 1000, 2),
                },
            )
            request_id_var.reset(token)


def _inbound_request_id(scope: dict) -> str | None:
    """Read X-Request-ID off the raw ASGI headers, if a caller sent one."""
    wanted = REQUEST_ID_HEADER.encode()
    for name, value in scope.get("headers") or ():
        if name.lower() == wanted:
            # Cap it: the id goes into log lines and a response header, and an
            # unbounded value from a caller has no business in either.
            return value.decode("latin-1")[:128] or None
    return None
