# Final deliverable — the EV capex signal service

The model, the data it reads and an HTTP server, in one Docker image. Start the
container, publish a port, and other software reads the model's per-company
signals off that port — by request (`GET /signals`) or as a push stream
(`GET /stream`).

```bash
# from the repository root
docker compose -f final-deliverable/docker-compose.yml up --build
curl localhost:8000/signals | python3 -m json.tool
```

## Status — read this before using the numbers

**This is scaffolding. The fitted model does not exist yet.** The container
currently serves a *null baseline*, and `/metadata` says so on every call:

```json
{ "model": { "name": "capex-intensity-baseline", "is_baseline": true } }
```

A consumer that must not act on the baseline should branch on
`model.is_baseline`.

The baseline is not a stub returning zeros. It emits cumulative **capex
intensity** — a company's total capex over its total depreciation across
FY23–FY26 — which is the one well-powered quantity the project has actually
established, from [`notebook-590/03_capex_panel_eda.ipynb`](../notebook-590/03_capex_panel_eda.ipynb)
section 11. Intensity above 1.0 means a firm is spending more on plant than it
writes off, so it is adding capacity rather than replacing it.

It carries **no EV features at all**, and that is the finding it encodes. The
notebook measured intensity at 2.06 for EV-led and battery names against 2.08
for components and ICE-led ones (t = −0.06, n = 35), and an ICE-only negative
control moved with the EV names. FY23–FY26 automotive capex looks like a
sector-wide cycle, not a response to EV volumes. So the baseline is the null
that a fitted model has to beat — and on its own it is still a useful
descriptive signal: how hard is this firm expanding, relative to its peers.

What is built and tested here is the **delivery mechanism**: the container, the
wire contract, the probes, the feature-store plumbing and the seam the model
drops into. See [Dropping the real model in](#dropping-the-real-model-in).

## The signal contract

Everything a consumer needs is on `/metadata`, and the machine-readable schema
is at `/docs` (Swagger) and `/openapi.json`.

| method | path | purpose |
|---|---|---|
| `GET` | `/health` | Liveness. 200 whenever the process is running. Never authenticated. |
| `GET` | `/ready` | Readiness. 200 when panel and model are loaded, 503 with the reason otherwise. Never authenticated. |
| `GET` | `/metadata` | Model identity, data provenance, scored companies, endpoint list. |
| `GET` | `/signals` | The full cross-section. Filters: `tier`, `direction`, `min_confidence`. |
| `GET` | `/signals/{nse_symbol}` | One company. Case-insensitive; percent-encode `&` in symbols like `ARE&M`. |
| `GET` | `/stream` | The same payload re-emitted as Server-Sent Events. `?interval=<seconds>` overrides the default. |
| `POST` | `/signals/refresh` | Force a re-read of the panel and model from disk. |
| `GET` | `/metrics` | Prometheus exposition. Behind the token when auth is on. |

A signal:

```json
{
  "nse_symbol": "ARE&M",
  "company": "Amara Raja Energy & Mobility Limited",
  "tier": "battery_cell",
  "score": 1.8976,
  "score_units": "ratio_capex_to_depreciation",
  "direction": "expand",
  "confidence": 1.0,
  "basis": {
    "cumulative_capex_cr": 3923.41,
    "cumulative_depreciation_cr": 2067.57,
    "filed_years": 4,
    "sector_median_intensity": 1.7332,
    "vs_sector_median": 0.1644,
    "latest_fiscal_period": "Q4 FY26",
    "latest_period_end": "2026-03-31"
  },
  "coverage": ["own_reg", "own_prod"],
  "notes": ["Baseline carries no EV features; see model.description."]
}
```

Reading it:

- **`score`** is model-native. Its meaning is in `score_units`, which changes
  when the model changes. Do not hard-code an interpretation of it.
- **`direction`** is the discretised form and is the stable thing to branch on:
  `expand` / `replace` / `contract`.
- **`confidence`** is `0.0`–`1.0`. For the baseline it is the share of the
  FY23–FY26 window the firm actually filed — **a data-coverage proxy, not a
  calibrated probability**, and emphatically not a confidence in the EV
  hypothesis, which the baseline does not test.
- **`basis`** carries the inputs behind `score`, so a consumer can audit a
  signal without re-reading the panel.
- **`coverage`** names which independent-variable series existed for that
  company-period (`production`, `own_reg`, `own_prod`). Most companies have
  none; only 6 of 52 have their own EV volume series at all.
- A company **absent** from the response could not be scored. 36 companies are
  in the panel and 35 are scored — the model skips rather than emitting a filler
  value, because a consumer can tell absent from zero but cannot tell a real
  zero from a fabricated one.

The envelope (`as_of`, `horizon`, `model`, `feature_store`, `count`) is attached
to every signal set, including each SSE event, so a stored payload is
self-describing months later.

### Consuming the stream

```bash
curl -N localhost:8000/stream          # SSE, one `signals` event per interval
```

```python
import httpx, json

with httpx.stream("GET", "http://localhost:8000/stream", timeout=None) as r:
    for line in r.iter_lines():
        if line.startswith("data:"):
            signals = json.loads(line.removeprefix("data:"))
            ...
```

SSE rather than WebSockets: the traffic is one-directional, SSE is plain HTTP so
it passes any proxy or ingress that already passes `/signals`, and `curl` can
read it. A consumer needing bidirectional traffic should put a broker between
itself and this container rather than change the contract.

Note that the baseline recomputes nothing between events — it is cumulative over
a static panel, so consecutive events are identical until the panel is
refreshed. The stream is there so a model that *does* move has somewhere to push
to.

## Configuration

Every knob is an environment variable, so one built image retargets without a
rebuild. An empty value is treated as unset, because orchestrators routinely
inject empty strings for keys they have no setting for.

| variable | default | meaning |
|---|---|---|
| `SIGNAL_PORT` | `8000` | Port the server binds. Change this **and** the published port together. |
| `SIGNAL_HOST` | `0.0.0.0` | Bind address. Must stay `0.0.0.0` in a container or the published port reaches nothing. |
| `FEATURE_STORE` | `/app/feature-store` | Directory holding `panel_company_annual.csv`. |
| `MODEL_ARTIFACT` | *(unset)* | Fitted artifact path. Unset ⇒ null baseline. Set but unloadable ⇒ **fatal**. |
| `SIGNAL_HORIZON` | `FY27` | Advisory label on the payload. |
| `SIGNAL_STREAM_INTERVAL` | `60` | Seconds between SSE events. |
| `SIGNAL_API_TOKEN` | *(unset)* | When set, bearer token required on everything except the probes. |
| `SIGNAL_CORS_ORIGINS` | *(unset)* | Comma-separated origins. Only needed for a browser consumer. |
| `SIGNAL_WATCH_FEATURE_STORE` | `true` | Re-read the panel when the file underneath it changes. |
| `LOG_LEVEL` | `INFO` | Standard Python level name. |
| `LOG_FORMAT` | `json` in the image, `text` from a checkout | `json` for a log aggregator, `text` for a terminal. |

A malformed value fails at import, before the port opens — a container that
would have served nonsense does not start.

## Deploying it

The image is self-contained: it bakes in the feature snapshot, so a given tag
always serves the same numbers. That is what makes a result reproducible months
later.

**The build context is the repository root**, not this directory, because the
image copies the panel from `data/`. `make build` and `docker compose` both set
it correctly; by hand:

```bash
docker build -f final-deliverable/Dockerfile -t ev-capex-signal:0.1.0 .
```

Building with `final-deliverable/` as the context fails on the data `COPY`,
which is the intended failure — an image without its feature snapshot has
nothing to serve.

```bash
# anywhere a Docker daemon runs
docker run -d -p 8000:8000 --name ev-capex-signal ev-capex-signal:0.1.0

# with auth, on a non-default port
docker run -d -p 9000:9000 \
  -e SIGNAL_PORT=9000 \
  -e SIGNAL_API_TOKEN="$(openssl rand -hex 24)" \
  ev-capex-signal:0.1.0
```

`docker-compose.yml` is the reference deployment shape — resource limits,
`no-new-privileges`, read-only root filesystem, healthcheck. On Kubernetes, map
the probes to **both** of them:

```yaml
livenessProbe:  { httpGet: { path: /health, port: 8000 } }
readinessProbe: { httpGet: { path: /ready,  port: 8000 } }
```

That split is the point of having two endpoints. A hung process should be
restarted; a healthy process that was handed a bad panel should merely be kept
out of the load balancer, because restarting it fixes nothing. Docker's own
`HEALTHCHECK` uses `/ready`, since that is what `depends_on:
condition: service_healthy` and Swarm rolling updates gate on.

### Observability

`GET /metrics` serves Prometheus exposition format. Alongside the usual process
collectors:

| series | type | use |
|---|---|---|
| `signal_http_requests_total` | counter | by method, **matched route** and status |
| `signal_http_request_duration_seconds` | histogram | buckets tuned to a millisecond-scale service, with a tail for `/stream` |
| `signal_service_ready` | gauge | `1`/`0`; the same condition as `/ready` |
| `signal_set_size` | gauge | companies in the current cross-section |
| `signal_set_computed_timestamp_seconds` | gauge | **subtract from `now()` to alert on staleness** |
| `signal_feature_store_rows` / `_mtime_seconds` | gauge | which panel is loaded |
| `signal_model_info` | info | name, version, `is_baseline`, `score_units` |
| `signal_model_reloads_total` | counter | by outcome: `ok` / `failed` / `error` |
| `signal_recomputes_total` | counter | by trigger: `panel_changed` / `ttl_expired` |
| `signal_sse_connections_active` | gauge | live `/stream` consumers |
| `signal_sse_events_total` | counter | by event type |

Requests are labelled by **route template**, never raw path. `/signals/{nse_symbol}`
has 35 live values and unbounded junk ones from anything that probes the port;
labelling by raw path would make each its own time series and eventually take the
scrape target down.

Logs go to stdout, one JSON object per line in the image (`LOG_FORMAT=text` for a
readable terminal). Every request produces exactly one access record carrying
duration, matched route, status and a request id:

```json
{"ts":"2026-10-09T12:53:16.512Z","level":"INFO","logger":"signal.access",
 "message":"GET /signals/M&M 200 0.9ms","request_id":"trace-from-caller",
 "http_method":"GET","http_path":"/signals/M&M",
 "http_route":"/signals/{nse_symbol}","http_status":200,"duration_ms":0.85}
```

An inbound `X-Request-ID` is honoured and echoed back, so a trace started by a
caller or an ingress survives into these logs; otherwise one is generated. It is
also attached to every log line emitted while handling that request, including
the service's own.

### Staleness

The cross-section is cached. Two different things can make that cache wrong, and
they get different answers:

- **The panel changed.** The service fingerprints the panel file (mtime + size)
  and reloads when it moves. So a panel rebuilt outside the container is picked
  up by the next request — no API call, no restart. `SIGNAL_WATCH_FEATURE_STORE=false`
  turns this off.
- **The model reads the clock.** A model that is a function of time as well as
  of the panel must declare `signal_ttl_s`; the service then recomputes the
  cross-section once that lapses, without re-parsing the panel. The baseline
  declares `None`, correctly — intensity is cumulative over a filed panel and
  reads no clock.

The same mechanism makes a container self-healing. One that starts before its
volume is attached comes up unready, and `/ready` — the endpoint an orchestrator
already polls — picks the panel up as soon as it appears. Verified: `RestartCount=0`.

`POST /signals/refresh` remains, for forcing it.

### Operating it

- **Refreshing the data without a rebuild** — mount the panel over the baked-in
  copy (there is a commented-out volume in `docker-compose.yml`). It is picked
  up automatically; see [Staleness](#staleness). A failed reload leaves the
  previous snapshot serving and reports the reason on `/ready`, so a bad rebuild
  upstream does not take the service down, and it is not retried on every
  request — only once the file changes again.
- **Diagnosing an unready container** — `curl localhost:8000/ready` returns the
  actual reason, e.g. a missing panel naming the path it looked at. The service
  deliberately starts unready rather than crash-looping: a crash loop tells an
  operator nothing, a container that serves its own diagnosis tells them what to
  fix.
- **Authentication** is off by default, which is correct only on a private
  network. Set `SIGNAL_API_TOKEN` before publishing the port anywhere wider. The
  probes stay open by design — an orchestrator has to probe before it has any
  reason to hold a secret, and neither probe discloses signal values.
- The container runs as a non-root user (uid 10001) with an unwritable `/app`.
  Nothing it does needs to write to disk.

## Testing

```bash
make venv && make test      # 72 tests, no Docker needed
make up && make smoke       # 17 checks against a running container
```

The suite runs against the repo's committed `data/processed/` rather than a
fixture CSV, on purpose: that way a schema change in `scripts/build_panel.py`
breaks the service's tests instead of being discovered after a deploy.

The image has been built and exercised in this environment. `docker compose up`
reports healthy in ~6s and the smoke test passes 17/17 against the container;
the signals it serves are numerically identical to a host run (35 signals,
sector median intensity 1.7332), which is the reproducibility claim the baked-in
snapshot is there to make. Also confirmed in-container: `docker run -p 8000:8000`
with no other flags, SIGTERM stopping the container in under a second (uvicorn
is PID 1), and a bad `MODEL_ARTIFACT` returning 503 with a mount hint and
driving the container to `unhealthy` in ~35s instead of silently serving the
baseline. Also verified in-container: one JSON access record per request with
an inbound `X-Request-ID` carried through, a panel rebuilt on the host picked up
by the next request (182 → 162 rows, 35 → 31 signals, attributed in
`signal_recomputes_total{reason="panel_changed"}`), and a container started
against an empty volume reaching ready once the panel appeared, with
`RestartCount=0`.

`scripts/smoke_test.sh` is the only check that exercises `/stream` over a real
socket. The suite cannot — both in-process ASGI clients (Starlette's
`TestClient` and httpx's `ASGITransport`) accumulate a response body and hand it
over only once the app finishes, and `/stream` is designed never to finish. So
the SSE generator is tested directly as a generator in `tests/test_stream.py`,
and the route itself is covered by the smoke test.

## Dropping the real model in

The seam is `app/model.py`. Everything above it talks to a `SignalModel`
protocol and knows nothing about how a signal is produced.

```python
class SignalModel(Protocol):
    name: str
    version: str
    description: str
    score_units: str
    required_features: tuple[str, ...]
    signal_ttl_s: float | None   # None = output is a pure function of the panel

    def signals(self, store: FeatureStore) -> list[RawSignal]: ...
```

1. Add the model's runtime dependencies to [`requirements.txt`](requirements.txt)
   — scikit-learn, joblib, statsmodels, whatever it needs. They are not there
   now because nothing uses them yet.
2. Implement `app/model.py::_load_artifact` to deserialise the artifact and
   return something satisfying the protocol.
3. Put the artifact under [`model/`](model/README.md) and set `MODEL_ARTIFACT`.
4. Extend `tests/test_model.py` — the protocol check that covers the baseline
   should cover the fitted model too, and the
   `test_present_but_unimplemented_artifact_fails_loudly` placeholder should be
   replaced by a test that loads a real fixture artifact.

`MODEL_ARTIFACT` set but unloadable is fatal rather than a quiet fallback to the
baseline. The two produce identical-looking responses, so a silent downgrade
would be discovered in the results rather than at deploy time.

Also worth updating when the model lands: `score_units` and the `confidence`
semantics, both of which are documented above as baseline-specific, and
`SIGNAL_HORIZON`, which the cumulative baseline does not really use.

Think about `signal_ttl_s` rather than copying the baseline's `None`. If the
model reads the clock anywhere — a decay term, a rolling window anchored to
today — it needs a TTL or it will serve its first answer for the life of the
container. There is a test asserting the baseline's `None` is deliberate, so
adding a time term there will fail loudly.

## Layout

```
final-deliverable/
  Dockerfile                 build context is the REPO ROOT, not here
  Dockerfile.dockerignore    exclusion list, kept beside the Dockerfile
  docker-compose.yml         local run + reference deployment shape
  Makefile                   build / up / test / smoke
  requirements.txt           serving deps only — fastapi, uvicorn, pydantic
  requirements-dev.txt       + pytest, httpx
  app/
    __main__.py              `python -m app`, the container's CMD
    main.py                  HTTP surface: routes, auth, SSE
    schemas.py               the wire contract
    service.py               holds the loaded (panel, model) pair
    model.py                 the model seam + the null baseline
    features.py              typed reader over the panel CSV
    observability.py         metrics, JSON logs, the request-timing middleware
    config.py                environment -> Settings
    healthcheck.py           `python -m app.healthcheck`, used by HEALTHCHECK
  model/                     fitted artifacts go here (empty; see its README)
  tests/                     72 tests
  scripts/smoke_test.sh      end-to-end check against a running container
```

## Design notes

**The serving path reads the panel; it does not re-derive it.** `scripts/` in
the repo root stays the single source of truth for feature construction. If the
service computed its own features there would be two implementations of the
panel logic and they would drift.

**No pandas in the image.** `app/features.py` is standard-library only, matching
`scripts/`. The panel is 182 rows, so pandas would buy nothing and add a large
dependency to the deployed surface. The fitted model may need numpy or
scikit-learn — add them when it lands, not before.

**One worker.** The model and panel are held in process memory and the workload
is a cached 35-row cross-section, so a second worker would double memory for no
throughput. Scale by running more containers, which is the unit this is shipped
in.

**No `request.is_disconnected()` polling in the SSE loop.** Starlette already
ends a `StreamingResponse` when the client disconnects. Polling would add a
second failure mode — the check blocks indefinitely under ASGI test transports —
for no benefit. The cost is that a disconnect during a long sleep is noticed
when the sleep ends; what is held until then is one idle coroutine.

### Known limits

- **No distributed tracing.** There are metrics and a request id that a caller
  can thread through, but no spans and no propagation to a downstream service.
  The request id is the seam to build that on if it is ever needed.
- **The base image is pinned, so patches no longer arrive on their own.** That
  is the trade for a reproducible build. The Dockerfile carries the one-liner
  that re-resolves the digest; refreshing it is a deliberate act now.
- **A recompute happens on the request that notices it.** One request pays for
  the reload while others wait on the lock. At a millisecond that is invisible;
  a model that takes seconds to score should move this to a background task
  rather than inherit this design.
- **`/metrics` does not trigger a freshness check.** A scrape observes state, it
  does not drive it, so between a panel changing and the next real request the
  gauges describe the panel still loaded. `signal_set_computed_timestamp_seconds`
  is there to make that visible rather than hidden.
