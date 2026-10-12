"""The push path.

Tests `signal_events` rather than a request to /stream. That is not a shortcut:
both in-process ASGI clients -- starlette's TestClient and httpx's
ASGITransport -- accumulate the response body and only hand it over once the
app has finished, so an endpoint that by design never finishes hangs them
instead of returning. The route's own headers and status over a real socket are
covered by scripts/smoke_test.sh against a running container.
"""
import asyncio
import dataclasses
import json

import pytest

from app.main import signal_events
from app.service import SignalService


async def _take(generator, count, timeout=10.0):
    """Pull `count` events, then close the generator.

    aclose() matters: without it the generator is left suspended and Python
    finalises it at an arbitrary later point, which under pytest surfaces as an
    unrelated test emitting a warning.
    """
    events = []
    try:
        async with asyncio.timeout(timeout):
            for _ in range(count):
                events.append(await anext(generator))
    finally:
        await generator.aclose()
    return events


def _parse(raw: bytes):
    text = raw.decode()
    assert text.endswith("\n\n"), "an SSE event is terminated by a blank line"
    lines = text.strip().split("\n")
    event = lines[0].removeprefix("event: ")
    data = json.loads(lines[1].removeprefix("data: "))
    return event, data


def test_first_event_arrives_without_waiting_an_interval(service):
    # A 60s period with a 5s timeout: if the generator slept before its first
    # yield this would time out rather than pass.
    (raw,) = asyncio.run(_take(signal_events(service, 60.0), 1, timeout=5.0))
    event, data = _parse(raw)
    assert event == "signals"
    assert data["count"] > 0
    assert data["model"]["name"] == "capex-intensity-baseline"


def test_payload_matches_the_pull_endpoint(service):
    (raw,) = asyncio.run(_take(signal_events(service, 60.0), 1, timeout=5.0))
    _, streamed = _parse(raw)
    pulled = json.loads(service.signal_set().model_dump_json())
    # as_of is computed once per load, so the two are comparable in full.
    assert streamed == pulled


def test_stream_keeps_emitting(service):
    events = asyncio.run(_take(signal_events(service, 0.05), 3, timeout=5.0))
    assert len(events) == 3
    assert all(_parse(raw)[0] == "signals" for raw in events)


def test_unready_service_emits_an_error_event_and_stays_open(settings, tmp_path):
    """A bad panel must not kill the connection.

    If the stream dropped here, every consumer would have to implement its own
    reconnect and backoff to survive a transient readiness blip.
    """
    broken = SignalService(dataclasses.replace(settings, feature_store=tmp_path))
    assert not broken.ready

    events = asyncio.run(_take(signal_events(broken, 0.05), 2, timeout=5.0))
    assert len(events) == 2, "the generator must keep going after an error event"
    for raw in events:
        event, data = _parse(raw)
        assert event == "error"
        assert "FEATURE_STORE" in data["detail"]


def test_generator_closes_cleanly(service):
    async def run():
        generator = signal_events(service, 60.0)
        await anext(generator)
        await generator.aclose()
        with pytest.raises(StopAsyncIteration):
            await anext(generator)

    asyncio.run(asyncio.wait_for(run(), timeout=5.0))
