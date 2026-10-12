"""Entry point: `python -m app`.

The Dockerfile calls this rather than `uvicorn app.main:app --port ...` so that
the listen address comes from the same Settings object as everything else. With
a CLI flag there would be two places a port can be set and one of them would
eventually be wrong.
"""
import uvicorn

from .config import settings


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        # Our own logging config is already installed by importing app.main;
        # letting uvicorn reconfigure it would replace the JSON formatter.
        log_config=None,
        log_level=settings.log_level.lower(),
        # One worker: the model and panel are held in process memory, and a
        # second worker would double that for no throughput gain on a workload
        # that is a cached 36-row cross-section. Scale by running more
        # containers, which is the unit the deliverable is shipped in.
        workers=1,
        # Off because ObservabilityMiddleware emits a richer access line --
        # same request, plus duration, matched route and request id, in one
        # record. Leaving both on would log every request twice.
        access_log=False,
    )


if __name__ == "__main__":
    main()
