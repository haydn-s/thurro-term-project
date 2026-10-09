#!/usr/bin/env bash
# Exercise every endpoint against a running container.
#
#   make up && make smoke
#   PORT=8080 ./scripts/smoke_test.sh
#   HOST=signals.internal PORT=443 SCHEME=https TOKEN=... ./scripts/smoke_test.sh
#
# This is the one check that covers the SSE route over a real socket. The test
# suite cannot: both in-process ASGI clients buffer a response until the app
# finishes, and /stream is designed never to finish.
set -euo pipefail

SCHEME="${SCHEME:-http}"
HOST="${HOST:-localhost}"
PORT="${PORT:-8000}"
BASE="${SCHEME}://${HOST}:${PORT}"
TOKEN="${TOKEN:-}"

pass=0
fail=0

# The last response body. A file rather than stdout so that callers can inspect
# a response without running check_status in a `$(...)` subshell -- which would
# discard the pass/fail counters it increments.
BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT

ok()   { printf '  \033[32mok\033[0m    %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=$((fail + 1)); }
note() { printf '  \033[33mnote\033[0m  %s\n' "$1"; }

# A wrapper rather than an array of curl flags: expanding an empty array under
# `set -u` is an error on bash 3.2, which is what /bin/bash still is on macOS.
req() {
  if [[ -n "$TOKEN" ]]; then
    curl -sS -H "Authorization: Bearer ${TOKEN}" "$@"
  else
    curl -sS "$@"
  fi
}

# Assert an endpoint's HTTP status, leaving the body in $BODY.
check_status() {
  local label="$1" method="$2" path="$3" want="$4" status
  status="$(req -o "$BODY" -w '%{http_code}' -X "$method" \
            --max-time 10 "${BASE}${path}" || echo 000)"
  if [[ "$status" == "$want" ]]; then
    ok "${label} (${method} ${path} -> ${status})"
    return 0
  fi
  bad "${label} (${method} ${path} -> ${status}, wanted ${want})"
  head -c 300 "$BODY"; echo
  return 1
}

# Read a field out of $BODY. jq is not assumed; python3 is already a dependency
# of this project.
field() { python3 -c "import json,sys; print(json.load(sys.stdin)$1)" < "$BODY"; }

echo "smoke test against ${BASE}"
echo
echo "probes"
check_status "liveness"  GET /health 200 || true
if check_status "readiness" GET /ready 200; then
  [[ "$(field "['status']")" == "ready" ]] \
    && ok "readiness reports ready" \
    || bad "readiness returned 200 but status is not 'ready'"
fi

echo
echo "integration"
if check_status "metadata" GET /metadata 200; then
  note "model: $(field "['model']['name']") v$(field "['model']['version']")"
  note "panel: $(field "['feature_store']['rows']") rows, \
$(field "['feature_store']['companies']") companies, \
latest $(field "['feature_store']['latest_period']")"
  note "scored: $(field "['companies'].__len__()") companies"
  if [[ "$(field "['model']['is_baseline']")" == "True" ]]; then
    note "serving the NULL BASELINE -- no fitted model is loaded"
  fi
fi

echo
echo "pull path"
symbol=""
if check_status "full cross-section" GET /signals 200; then
  count="$(field "['count']")"
  [[ "$count" -gt 0 ]] && ok "returned ${count} signals" || bad "returned no signals"
  symbol="$(field "['signals'][0]['nse_symbol']")"
fi

if [[ -n "$symbol" ]]; then
  # NSE symbols contain & and -, so the path segment has to be encoded.
  encoded="$(python3 -c "import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=''))" "$symbol")"
  check_status "single company (${symbol})" GET "/signals/${encoded}" 200 || true
fi
check_status "unknown company is 404" GET "/signals/NOTAREALSYMBOL" 404 || true
check_status "tier filter"            GET "/signals?tier=oem_ev_led" 200 || true
check_status "bad direction is 422"   GET "/signals?direction=sideways" 422 || true
check_status "refresh"                POST /signals/refresh 200 || true

echo
echo "observability"
if check_status "metrics" GET /metrics 200; then
  series=0
  for name in signal_http_requests_total signal_service_ready signal_set_size \
              signal_feature_store_rows signal_model_info; do
    grep -q "^${name}" "$BODY" && series=$((series + 1)) \
      || bad "metrics is missing ${name}"
  done
  [[ "$series" -eq 5 ]] && ok "all 5 core metric families present"
  # Raw paths in a label would make every probed URL its own time series.
  if grep -q 'route="/signals/{nse_symbol}"' "$BODY"; then
    ok "requests are labelled by route template, not raw path"
  else
    bad "no route-template label found in metrics"
  fi
fi

# The middleware has to be in the path for a STREAMING response too -- that is
# the whole reason it is pure ASGI rather than BaseHTTPMiddleware.
rid="smoke-$$"
hdrs="$(req -N -D - -o /dev/null --max-time 3 -H "X-Request-ID: ${rid}" \
        "${BASE}/stream?interval=1" 2>/dev/null || true)"
if grep -qi "^x-request-id: ${rid}" <<<"$hdrs"; then
  ok "request id survives into a streaming response"
else
  bad "X-Request-ID missing from /stream response headers"
fi

echo
echo "push path"
# -N disables curl's buffering; --max-time ends the otherwise endless stream.
stream="$(req -N --max-time 4 "${BASE}/stream?interval=1" 2>/dev/null || true)"
emitted="$(grep -c '^event: signals' <<<"$stream" || true)"
if [[ "${emitted:-0}" -ge 2 ]]; then
  ok "SSE emitted ${emitted} events in 4s at interval=1"
else
  bad "SSE emitted ${emitted:-0} events in 4s, wanted >= 2"
fi
if grep -q '^data: {' <<<"$stream"; then
  ok "SSE data lines carry JSON"
else
  bad "SSE data lines are not JSON"
fi

echo
echo "${pass} passed, ${fail} failed"
exit $(( fail > 0 ? 1 : 0 ))
