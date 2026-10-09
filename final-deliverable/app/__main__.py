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
        log_level=settings.log_level.lower(),
        # One worker: the model and panel are held in process memory, and a
        # second worker would double that for no throughput gain on a workload
        # that is a cached 36-row cross-section. Scale by running more
        # containers, which is the unit the deliverable is shipped in.
        workers=1,
        access_log=True,
    )


if __name__ == "__main__":
    main()
