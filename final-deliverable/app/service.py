"""Wires the feature store and the model together, and holds the served state.

One instance lives for the life of the process. It owns the loaded snapshot and
the loaded model, and it is the only thing that replaces either -- so a request
never sees a half-swapped pair.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .features import FeatureStore, FeatureStoreError
from .model import ModelArtifactError, RawSignal, SignalModel, load_model
from .schemas import (
    FeatureStoreInfo,
    ModelInfo,
    Signal,
    SignalSet,
)

log = logging.getLogger(__name__)


class SignalService:
    """Serves signals from a loaded (store, model) pair.

    Construction never raises: if the panel or the artifact is bad the service
    comes up unready and says why on /ready, rather than crash-looping. A
    crash-looping container tells an operator nothing; an unready one that
    serves its own diagnosis tells them exactly what to fix. Liveness and
    readiness are separate probes precisely so this distinction survives.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store: FeatureStore | None = None
        self.model: SignalModel | None = None
        self.load_error: str | None = None
        self._signals: list[RawSignal] = []
        self._computed_at: datetime | None = None
        self.reload()

    # -- lifecycle -------------------------------------------------------

    def reload(self) -> None:
        """(Re)load the panel and the model, then recompute the cross-section.

        Loads into locals first and only publishes on success, so a failed
        refresh leaves the previously good state serving traffic.
        """
        try:
            store = FeatureStore.load(self.settings.feature_store)
            model = load_model(self.settings.model_artifact)
            signals = model.signals(store)
        except (FeatureStoreError, ModelArtifactError) as exc:
            self.load_error = str(exc)
            log.error("signal service not ready: %s", exc)
            return
        except Exception as exc:  # noqa: BLE001 - last resort, reported not swallowed
            self.load_error = f"unexpected error loading model or panel: {exc!r}"
            log.exception("signal service not ready")
            return

        self.store = store
        self.model = model
        self._signals = signals
        self._computed_at = datetime.now(timezone.utc)
        self.load_error = None
        log.info(
            "loaded %s v%s over %d panel rows -> %d signals",
            model.name, model.version, len(store.rows), len(signals),
        )

    @property
    def ready(self) -> bool:
        return self.store is not None and self.model is not None

    def require_ready(self) -> None:
        if not self.ready:
            raise ServiceNotReady(self.load_error or "service is still starting")

    # -- descriptions ----------------------------------------------------

    def model_info(self) -> ModelInfo:
        self.require_ready()
        assert self.model is not None
        artifact: Path | None = self.settings.model_artifact
        return ModelInfo(
            name=self.model.name,
            version=self.model.version,
            description=self.model.description,
            score_units=self.model.score_units,
            required_features=list(self.model.required_features),
            artifact=str(artifact) if artifact else None,
            is_baseline=artifact is None,
        )

    def store_info(self) -> FeatureStoreInfo:
        self.require_ready()
        assert self.store is not None
        return FeatureStoreInfo(
            source=str(self.store.source),
            rows=len(self.store.rows),
            companies=len(self.store.symbols()),
            periods=len(self.store.periods()),
            latest_period=self.store.latest_period(),
            loaded_at=self.store.loaded_at,
            source_mtime=self.store.source_mtime,
        )

    # -- signals ---------------------------------------------------------

    def signal_set(
        self,
        tier: str | None = None,
        direction: str | None = None,
        min_confidence: float = 0.0,
    ) -> SignalSet:
        self.require_ready()
        rows = [
            self._to_wire(s)
            for s in self._signals
            if (tier is None or s.tier == tier)
            and (direction is None or s.direction == direction)
            and s.confidence >= min_confidence
        ]
        return SignalSet(
            as_of=self._computed_at or datetime.now(timezone.utc),
            horizon=self.settings.signal_horizon,
            model=self.model_info(),
            feature_store=self.store_info(),
            count=len(rows),
            signals=rows,
        )

    def signal_for(self, symbol: str) -> Signal | None:
        """One company, matched case-insensitively on NSE symbol.

        Symbols in the panel carry punctuation (`M&M`, `BAJAJ-AUTO`, `ARE&M`), so
        a consumer passing one in a URL will have percent-encoded it; FastAPI has
        already decoded it by here. Case folding is a convenience -- the panel's
        own casing is what comes back in the response.
        """
        self.require_ready()
        wanted = symbol.strip().upper()
        for signal in self._signals:
            if signal.nse_symbol.upper() == wanted:
                return self._to_wire(signal)
        return None

    def known_symbols(self) -> list[str]:
        return sorted(s.nse_symbol for s in self._signals)

    def known_tiers(self) -> list[str]:
        return sorted({s.tier for s in self._signals})

    def signal_count(self) -> int:
        return len(self._signals)

    @staticmethod
    def _to_wire(signal: RawSignal) -> Signal:
        return Signal(
            nse_symbol=signal.nse_symbol,
            company=signal.company,
            tier=signal.tier,
            score=signal.score,
            score_units=signal.score_units,
            direction=signal.direction,
            confidence=signal.confidence,
            basis=signal.basis,
            coverage=list(signal.coverage),
            notes=list(signal.notes),
        )


class ServiceNotReady(RuntimeError):
    """Raised when a signal endpoint is hit before the model/panel loaded."""
