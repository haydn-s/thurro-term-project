"""Container healthcheck: `python -m app.healthcheck [path]`.

A module rather than an inline `HEALTHCHECK CMD` one-liner, because the inline
form has to be quote-escaped through the Dockerfile and is then impossible to
test. Uses only the standard library, so the runtime image needs no curl.

Defaults to /ready rather than /health: Docker's own health state is what
`depends_on: condition: service_healthy` and Swarm rolling updates gate on, and
those should wait for a container that can actually answer, not merely one whose
process is alive. Kubernetes has two probes and should use both -- livenessProbe
on /health, readinessProbe on /ready.
"""
import sys
import urllib.error
import urllib.request

from .config import settings


def probe(path: str = "/ready", timeout: float = 4.0) -> int:
    # 127.0.0.1, not settings.host: the server binds 0.0.0.0 but this check runs
    # inside the same namespace and should not depend on external routing.
    url = f"http://127.0.0.1:{settings.port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 0 if response.status == 200 else 1
    except urllib.error.HTTPError as exc:
        # A 503 from /ready is a healthy process with bad inputs. Unhealthy for
        # the purposes of receiving traffic, which is what this gates.
        print(f"{url} -> HTTP {exc.code}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - any failure is an unhealthy verdict
        print(f"{url} -> {exc!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(probe(sys.argv[1] if len(sys.argv) > 1 else "/ready"))
