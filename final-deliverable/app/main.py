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
from fastapi.responses import JSONResponse, StreamingResponse

from . import __version__
from .config import settings
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

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
log = logging.getLogger(SERVICE_NAME)

#: Populated in the lifespan handler. Module-level rather than app.state so the
#: route signatures stay readable; there is exactly one per process.
service: SignalService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global service
    log.info(
        "starting %s v%s  feature_store=%s  model_artifact=%s  auth=%s",
        SERVICE_NAME, __version__, settings.feature_store,
        settings.model_artifact or "<none, serving null baseline>",
        "on" if settings.requires_auth else "off",
    )
    # Loading happens here rather than per-request: the panel is small, and a
    # container that has already read its inputs can answer /ready honestly
    # before any traffic arrives.
    service = SignalService(settings)
    if not service.ready:
        log.error("started UNREADY: %s", service.load_error)
    yield
    log.info("shutting down")


app = FastAPI(
    title="EV capex signal service",
    version=__version__,
    summary="Per-company automotive capex expansion signals, served over HTTP.",
    description=__doc__,
    lifespan=lifespan,
)

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
    return Metadata(
        service=SERVICE_NAME,
        version=__version__,
        horizon=settings.signal_horizon,
        model=svc.model_info(),
        feature_store=svc.store_info(),
        stream_interval_s=settings.stream_interval_s,
        auth_required=settings.requires_auth,
        tiers=svc.known_tiers(),
        companies=svc.known_symbols(),
        endpoints=ENDPOINTS,
    )


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
    while True:
        try:
            yield _sse("signals", svc.signal_set().model_dump_json())
        except ServiceNotReady as exc:
            # Report and hold the connection open: readiness is usually
            # transient, and dropping the stream would make every consumer
            # implement its own reconnect.
            yield _sse("error", json.dumps({"detail": str(exc)}))
        await asyncio.sleep(period)


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
