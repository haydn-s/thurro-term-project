"""Runtime configuration, read entirely from the environment.

Every knob the container has is an environment variable, so one built image can
be handed to any Docker manager -- Compose, Swarm, ECS, Kubernetes, a bare
`docker run` -- and retargeted without a rebuild. The defaults are chosen so
that

    docker run -p 8000:8000 ev-capex-signal

serves signals with no flags at all, reading the feature snapshot that was baked
into the image at build time.
"""
import os
from dataclasses import dataclass
from pathlib import Path

# /app inside the image; the repo's final-deliverable/ when run from a checkout.
APP_ROOT = Path(__file__).resolve().parent.parent


def _env_str(name: str, default: str) -> str:
    # An env var set to the empty string is treated as unset. Orchestrators
    # routinely inject empty values for keys they have no setting for, and
    # silently binding to "" or opening an unauthenticated port because of that
    # would be worse than ignoring it.
    value = os.environ.get(name, "").strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = _env_str(name, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _env_flag(name: str, default: bool) -> bool:
    raw = _env_str(name, "true" if default else "false").lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be a boolean, got {raw!r}")


class ConfigError(RuntimeError):
    """Raised on a malformed environment, before the server starts listening."""


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    feature_store: Path
    model_artifact: Path | None
    signal_horizon: str
    stream_interval_s: float
    api_token: str | None
    log_level: str
    log_format: str
    watch_feature_store: bool
    cors_origins: tuple[str, ...]

    @property
    def requires_auth(self) -> bool:
        return self.api_token is not None

    @classmethod
    def from_env(cls) -> "Settings":
        artifact = _env_str("MODEL_ARTIFACT", "")
        token = _env_str("SIGNAL_API_TOKEN", "")
        origins = _env_str("SIGNAL_CORS_ORIGINS", "")

        port = _env_int("SIGNAL_PORT", 8000)
        if not 1 <= port <= 65535:
            raise ConfigError(f"SIGNAL_PORT out of range: {port}")

        fmt = _env_str("LOG_FORMAT", "text").lower()
        if fmt not in ("text", "json"):
            raise ConfigError(f"LOG_FORMAT must be 'text' or 'json', got {fmt!r}")

        interval = _env_float("SIGNAL_STREAM_INTERVAL", 60.0)
        if interval <= 0:
            raise ConfigError(f"SIGNAL_STREAM_INTERVAL must be positive: {interval}")

        return cls(
            # 0.0.0.0 is deliberate and is the point of the deliverable: the
            # process has to accept connections from outside its own network
            # namespace or the published port reaches nothing. Exposure is
            # controlled by what the operator publishes with -p, not by binding
            # to loopback here.
            host=_env_str("SIGNAL_HOST", "0.0.0.0"),
            port=port,
            feature_store=Path(_env_str("FEATURE_STORE", str(APP_ROOT / "feature-store"))),
            model_artifact=Path(artifact) if artifact else None,
            signal_horizon=_env_str("SIGNAL_HORIZON", "FY27"),
            stream_interval_s=interval,
            api_token=token or None,
            log_level=_env_str("LOG_LEVEL", "INFO").upper(),
            # Text by default so running from a checkout stays readable; the
            # Dockerfile sets json, because the image's output goes to a log
            # aggregator rather than to a person's terminal.
            log_format=_env_str("LOG_FORMAT", "text").lower(),
            # Re-read the panel when the file underneath changes. On by default:
            # a mounted, rebuilt panel otherwise serves stale signals until
            # someone remembers to POST /signals/refresh.
            watch_feature_store=_env_flag("SIGNAL_WATCH_FEATURE_STORE", True),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        )


settings = Settings.from_env()
