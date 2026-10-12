"""HTTP surface: the port the signals leave the container on.

Two ways out, because consumers differ:

  pull   GET /signals        -- the whole cross-section, on request
  push   GET /stream         -- the same payload re-emitted as Server-Sent
                                Events, for software that wants to react rather
                                than poll

SSE rather than WebSockets for the push path: the traffic is one-directional
(the container never needs to hear back), SSE is plain HTTP so it survives any
proxy or ingress that already passes the pull path, and `curl` can read it. A
consumer that genuinely needs bidirectional traffic should put a broker between
itself and this container rather than change this contract.
"""
import asyncio
import json
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response as RawResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from . import __version__
from .config import settings
from .observability import (
    ObservabilityMiddleware,
    tracer,
    configure_logging,
    render_metrics,
    set_service_state,
    sse_connections,
    sse_events,
)
from .schemas import (
    Endpoint,
    Health,
    Metadata,
    Ready,
    RefreshResult,
    Signal,
    SignalSet,
)
from .service import ServiceNotReady, SignalService

SERVICE_NAME = "ev-capex-signal"

configure_logging(settings.log_level, settings.log_format)
log = logging.getLogger(SERVICE_NAME)

#: Populated in the lifespan handler. Module-level rather than app.state so the
#: route signatures stay readable; there is exactly one per process.
service: SignalService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global service
    log.info(
        "starting %s v%s  feature_store=%s  model_artifact=%s  auth=%s  tracing=%s",
        SERVICE_NAME, __version__, settings.feature_store,
        settings.model_artifact or "<none, serving null baseline>",
        "on" if settings.requires_auth else "off",
        settings.otel_endpoint if settings.tracing_enabled else "off",
    )
    # Loading happens here rather than per-request: the panel is small, and a
    # container that has already read its inputs can answer /ready honestly
    # before any traffic arrives.
    #
    # Wrapped in a span so the startup load is ONE trace. Without a parent,
    # the spans inside SignalService -- feature_store.load, model.load,
    # model.signals -- each became a separate single-span trace with no context,
    # because at startup there is no request span to attach to. Three orphans in
    # a trace backend tell you nothing; one `service.startup` tree tells you how
    # long the container took to become useful and which part was slow.
    with tracer.start_as_current_span("service.startup") as span:
        service = SignalService(settings)
        span.set_attribute("service.ready", service.ready)
        span.set_attribute("service.version", __version__)
        if service.store is not None:
            span.set_attribute("panel.rows", len(service.store.rows))
    if not service.ready:
        log.error("started UNREADY: %s", service.load_error)
    yield
    log.info("shutting down")


#: Paths kept out of traces. The healthcheck hits /ready every 10s and a
#: Prometheus scrape hits /metrics on its own interval, so tracing them would
#: fill a backend with identical spans nobody will ever read and bill for the
#: privilege. Their failures are already visible in metrics and logs.
TRACE_EXCLUDED_PATHS = frozenset({"/health", "/ready", "/metrics"})


def _exclude_from_traces(scope: dict) -> bool:
    return scope.get("path") in TRACE_EXCLUDED_PATHS


app = FastAPI(
    title="EV capex signal service",
    version=__version__,
    summary="Per-company automotive capex expansion signals, served over HTTP.",
    description=__doc__,
    lifespan=lifespan,
    # FastAPI 0.143 instruments itself; there is no bolt-on package here. It
    # extracts W3C traceparent on the way in, so a consumer that calls
    # /signals as part of its own workflow sees this request inside its trace.
    telemetry={
        "tracing": True,
        # Spans for dependency resolution, the endpoint and serialization. This
        # service makes no outbound calls, so without these -- and the explicit
        # spans in service.py -- a trace would be one flat span saying only how
        # long the whole request took.
        "operation_spans": True,
        # Off: Prometheus already owns metrics (/metrics) and logging is already
        # configured above. Turning these on would mean two metrics pipelines
        # double-counting the same requests, and two log pipelines emitting the
        # same records.
        "metrics": False,
        "logs": False,
        # Reads the standard OTEL_* variables and adds an OTLP exporter only if
        # an endpoint is set. With none set it returns early, so this is a no-op
        # by default and the deliverable still runs with zero configuration.
        "auto_configure": True,
        "exclude": _exclude_from_traces,
    },
)

# Added before CORS so it ends up outermost: Starlette applies middleware in
# reverse registration order, and the access log should cover a request even
# when CORS rejects it.
app.add_middleware(ObservabilityMiddleware)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.exception_handler(ServiceNotReady)
async def _not_ready(request: Request, exc: ServiceNotReady) -> JSONResponse:
    # 503 rather than 500: the request was fine, the container is not yet able
    # to answer it, and a load balancer should read that as "retry elsewhere".
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(exc)}
    )


def get_service() -> SignalService:
    if service is None:  # pragma: no cover - lifespan always runs first
        raise ServiceNotReady("service has not started")
    return service


def require_token(request: Request) -> None:
    """Bearer-token gate, active only when SIGNAL_API_TOKEN is set.

    Off by default so the container is useful the moment it starts; an operator
    publishing the port to anything wider than a private network should set the
    variable. `/health` and `/ready` are intentionally left open -- an
    orchestrator has to probe them before it has any reason to hold a secret,
    and neither discloses signal values.
    """
    if not settings.requires_auth:
        return
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    assert settings.api_token is not None
    # compare_digest, not ==, so a wrong token cannot be found a character at a
    # time from response timing.
    if scheme.lower() != "bearer" or not secrets.compare_digest(token, settings.api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


Protected = Depends(require_token)

ENDPOINTS = [
    Endpoint(path="/health", method="GET", summary="Liveness; always 200 while the process runs."),
    Endpoint(path="/ready", method="GET", summary="Readiness; 503 until panel and model load."),
    Endpoint(path="/metadata", method="GET", summary="Model, data provenance and integration details."),
    Endpoint(path="/signals", method="GET", summary="Full cross-section of signals."),
    Endpoint(path="/signals/{nse_symbol}", method="GET", summary="One company's signal."),
    Endpoint(path="/stream", method="GET", summary="Server-Sent Events; re-emits the set on an interval."),
    Endpoint(path="/signals/refresh", method="POST", summary="Reload the panel and model from disk."),
    Endpoint(path="/metrics", method="GET", summary="Prometheus metrics."),
]


# -- probes ---------------------------------------------------------------
# Separate liveness and readiness so an orchestrator restarts a hung process but
# merely withholds traffic from one whose inputs are wrong. A single endpoint
# conflates "this process is broken" with "this process was handed a bad panel",
# and the remedies differ.

@app.get("/health", response_model=Health, tags=["probes"])
def health() -> Health:
    return Health(service=SERVICE_NAME, version=__version__)


@app.get("/ready", response_model=Ready, tags=["probes"])
def ready(response: Response, svc: SignalService = Depends(get_service)) -> Ready:
    # The freshness check belongs here, not only on the read path. This is the
    # endpoint an orchestrator already polls, so a container that came up before
    # its volume was attached recovers on its own -- fix the mount and the next
    # probe loads the panel. Without this, self-healing needed a /signals
    # request, which a load balancer will never send to a container it believes
    # is unready. The check is one stat() call.
    svc.ensure_fresh()
    if svc.ready:
        return Ready(status="ready", model_loaded=True, feature_store_loaded=True)
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Ready(
        status="not_ready",
        model_loaded=svc.model is not None,
        feature_store_loaded=svc.store is not None,
        detail=svc.load_error,
    )


# -- integration ----------------------------------------------------------

@app.get("/", include_in_schema=False)
def index() -> dict[str, str]:
    return {
        "service": SERVICE_NAME,
        "version": __version__,
        "signals": "/signals",
        "stream": "/stream",
        "metadata": "/metadata",
        "openapi": "/docs",
    }


@app.get("/metadata", response_model=Metadata, tags=["integration"],
         dependencies=[Protected])
def metadata(svc: SignalService = Depends(get_service)) -> Metadata:
    # This endpoint reports the panel's row count, latest period and mtime. A
    # consumer reads it to know what the signals were computed from, so serving
    # provenance for a panel that has since been replaced is worse than useless.
    svc.ensure_fresh()
    return Metadata(
        service=SERVICE_NAME,
        version=__version__,
        horizon=settings.signal_horizon,
        model=svc.model_info(),
        feature_store=svc.store_info(),
        stream_interval_s=settings.stream_interval_s,
        auth_required=settings.requires_auth,
        tracing=settings.tracing_enabled,
        tiers=svc.known_tiers(),
        companies=svc.known_symbols(),
        endpoints=ENDPOINTS,
    )


@app.get("/metrics", tags=["probes"], dependencies=[Protected],
         include_in_schema=False)
def metrics(svc: SignalService = Depends(get_service)) -> RawResponse:
    """Prometheus exposition format.

    Behind the same token as /signals rather than open like the probes. It
    discloses no signal values, but it does name the model and its version, and
    that is not something to volunteer on a published port. Prometheus can carry
    a bearer token in its scrape config.

    State gauges are refreshed here, at scrape time, so they cannot drift from
    what the service would actually answer with.
    """
    set_service_state(svc)
    body, content_type = render_metrics()
    return RawResponse(content=body, media_type=content_type)


# -- signals --------------------------------------------------------------

@app.get("/signals", response_model=SignalSet, tags=["signals"],
         dependencies=[Protected])
def get_signals(
    svc: SignalService = Depends(get_service),
    tier: str | None = Query(default=None, description="Exact tier match, e.g. oem_ev_led."),
    direction: str | None = Query(default=None, pattern="^(expand|replace|contract)$"),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
) -> SignalSet:
    return svc.signal_set(tier=tier, direction=direction, min_confidence=min_confidence)


# Registered before /signals/{nse_symbol} on purpose: FastAPI matches in
# declaration order, and the other way round a POST to /signals/refresh would be
# read as a symbol named "refresh".
@app.post("/signals/refresh", response_model=RefreshResult, tags=["signals"],
          dependencies=[Protected])
def refresh(svc: SignalService = Depends(get_service)) -> RefreshResult:
    """Re-read the panel and the model artifact from disk.

    For the case where FEATURE_STORE is a mounted volume and the panel has been
    rebuilt: the data changes without the image changing, so there is nothing to
    redeploy. A failed reload keeps the previous snapshot serving and surfaces
    the reason on /ready.
    """
    svc.reload()
    svc.require_ready()
    return RefreshResult(
        status="refreshed",
        feature_store=svc.store_info(),
        model=svc.model_info(),
        signals=svc.signal_count(),
    )


@app.get("/signals/{nse_symbol}", response_model=Signal, tags=["signals"],
         dependencies=[Protected])
def get_signal(
    nse_symbol: str, svc: SignalService = Depends(get_service)
) -> Signal:
    found = svc.signal_for(nse_symbol)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no signal for {nse_symbol!r}. A company in the panel can still "
                   f"be absent here if the model could not score it; GET /metadata "
                   f"lists the symbols that are scored.",
        )
    return found


# -- push path ------------------------------------------------------------

def _sse(event: str, payload: str) -> bytes:
    """Frame one Server-Sent Event.

    Two newlines terminate an event; a consumer that reads one newline sees a
    half event, so the blank line is the contract, not formatting.
    """
    return f"event: {event}\ndata: {payload}\n\n".encode()


async def signal_events(svc: SignalService, period: float) -> AsyncIterator[bytes]:
    """The push path's body, as a generator.

    Factored out of the route so it can be tested directly. It has to be: both
    of the in-process ASGI clients buffer a response until the app finishes, so
    an endpoint that never finishes cannot be driven through either one. The
    route over a real socket is covered by scripts/smoke_test.sh instead.

    There is no `request.is_disconnected()` polling here, on purpose. Starlette
    already ends a StreamingResponse when the client disconnects -- on modern
    ASGI servers the next `send()` raises, on older ones a task group cancels
    the generator -- so polling would add nothing but a second failure mode.
    The one cost is that a disconnect during a long sleep is noticed when that
    sleep ends; what is held until then is one idle coroutine, not a worker.
    """
    sse_connections.inc()
    try:
        while True:
            try:
                # run_in_threadpool because signal_set() may now recompute the
                # cross-section under a lock. For the baseline that is about a
                # millisecond, but a heavier model would stall the event loop --
                # and with it every other connection this process is serving.
                payload = await run_in_threadpool(
                    lambda: svc.signal_set().model_dump_json()
                )
                yield _sse("signals", payload)
                sse_events.labels("signals").inc()
            except ServiceNotReady as exc:
                # Report and hold the connection open: readiness is usually
                # transient, and dropping the stream would make every consumer
                # implement its own reconnect.
                yield _sse("error", json.dumps({"detail": str(exc)}))
                sse_events.labels("error").inc()
            await asyncio.sleep(period)
    finally:
        # Runs on client disconnect, on cancellation and on shutdown, so the
        # gauge cannot leak a connection that has gone away.
        sse_connections.dec()


@app.get("/stream", tags=["signals"], dependencies=[Protected],
         response_class=StreamingResponse)
async def stream(
    svc: SignalService = Depends(get_service),
    interval: float | None = Query(
        default=None, gt=0, le=3600,
        description="Override SIGNAL_STREAM_INTERVAL for this connection, seconds.",
    ),
) -> StreamingResponse:
    """Re-emit the signal set as SSE until the client goes away.

    The first event is sent immediately, so a consumer does not wait a full
    interval to learn the current state.
    """
    return StreamingResponse(
        signal_events(svc, interval or settings.stream_interval_s),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Tells nginx-style proxies not to buffer, which would otherwise
            # hold events until the response "finished" -- i.e. never.
            "X-Accel-Buffering": "no",
        },
    )
