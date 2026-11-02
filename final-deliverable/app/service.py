"""Wires the feature store, the model and the outlook together, and holds the served state.

One instance lives for the life of the process. It owns the loaded snapshot, the
loaded model and the loaded outlook, and it is the only thing that replaces any
of them -- so a request never sees a half-swapped set.
"""
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import Settings
from .features import ANNUAL_PANEL, FeatureStore, FeatureStoreError
from .model import ModelArtifactError, RawSignal, SignalModel, load_model
from .observability import model_reloads, signal_recomputes, tracer
from .outlook import (
    LogitModel,
    Outlook,
    OutlookArtifactError,
    Scored,
    add_months,
    month_closed,
)
from .schemas import (
    Contribution,
    FeatureStoreInfo,
    ModelInfo,
    NationalOutlook,
    OutlookInfo,
    OutlookModelInfo,
    OutlookModelRef,
    Signal,
    SignalSet,
    StateOutlook,
    StateOutlookEntry,
)

#: A stat() result reduced to what changes on a rewrite, or None if unreadable.
_FileId = tuple[int, int] | None

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
        self.outlook: Outlook | None = None
        self.load_error: str | None = None
        self._signals: list[RawSignal] = []
        self._computed_at: datetime | None = None
        # Identity of the panel and outlook files the current state was built
        # from, so a change on disk is detectable without re-parsing either.
        self._fingerprint: tuple[_FileId, _FileId] | None = None
        # FastAPI runs sync endpoints in a threadpool, so two requests can hit
        # the freshness check at once. Everything that reads or replaces the
        # cached state does so under this lock; it is reentrant because reload()
        # is reachable both directly and from ensure_fresh().
        self._lock = threading.RLock()
        self.reload()

    @property
    def computed_at(self) -> datetime | None:
        """When the cached cross-section was computed. Read by /metrics."""
        return self._computed_at

    # -- lifecycle -------------------------------------------------------

    def reload(self) -> None:
        """(Re)load the panel, the model and the outlook, then recompute the cross-section.

        Loads into locals first and only publishes on success, so a failed
        refresh leaves the previously good state serving traffic.
        """
        with self._lock:
            # Recorded before the attempt, not after, so a reload that fails is
            # not retried on every single request -- only once the file that
            # failed actually changes.
            self._fingerprint = self._input_fingerprint()
            try:
                # Named spans for the three distinct costs, because "the request
                # was slow" and "parsing the panel was slow" need different
                # fixes. FastAPI's own spans cannot see inside this.
                with tracer.start_as_current_span("feature_store.load") as span:
                    store = FeatureStore.load(self.settings.feature_store)
                    span.set_attribute("panel.rows", len(store.rows))
                    span.set_attribute("panel.source", str(store.source))
                with tracer.start_as_current_span("model.load"):
                    model = load_model(self.settings.model_artifact)
                with tracer.start_as_current_span("model.signals") as span:
                    signals = model.signals(store)
                    span.set_attribute("model.name", model.name)
                    span.set_attribute("model.version", model.version)
                    span.set_attribute("signals.count", len(signals))
                with tracer.start_as_current_span("outlook.load") as span:
                    outlook = Outlook.load(self.settings.outlook_artifact)
                    span.set_attribute("outlook.national.version", outlook.national.version)
                    span.set_attribute("outlook.state.version", outlook.state.version)
            except (FeatureStoreError, ModelArtifactError, OutlookArtifactError) as exc:
                self.load_error = str(exc)
                model_reloads.labels("failed").inc()
                log.error("signal service not ready: %s", exc)
                return
            except Exception as exc:  # noqa: BLE001 - last resort, reported not swallowed
                self.load_error = f"unexpected error loading model or panel: {exc!r}"
                model_reloads.labels("error").inc()
                log.exception("signal service not ready")
                return

            self.store = store
            self.model = model
            self.outlook = outlook
            self._signals = signals
            self._computed_at = datetime.now(timezone.utc)
            self.load_error = None
            model_reloads.labels("ok").inc()
            log.info(
                "loaded %s v%s over %d panel rows -> %d signals (ttl=%s); "
                "outlook %s / %s for %s",
                model.name, model.version, len(store.rows), len(signals),
                model.signal_ttl_s if model.signal_ttl_s is not None else "none",
                outlook.national.version, outlook.state.version,
                add_months(outlook.national_month, outlook.national.horizon_months),
                extra={
                    "model_name": model.name,
                    "model_version": model.version,
                    "panel_rows": len(store.rows),
                    "signals": len(signals),
                    "outlook_national_version": outlook.national.version,
                    "outlook_state_version": outlook.state.version,
                },
            )

    # -- freshness -------------------------------------------------------

    def _input_fingerprint(self) -> tuple[_FileId, _FileId]:
        """(mtime_ns, size) of the panel and of the outlook artifact.

        Both parts matter. mtime alone misses a rewrite inside the same
        filesystem timestamp granularity, and size alone misses an edit that
        happens to preserve the byte count. Together they catch every rebuild
        this pipeline actually produces. A content hash would be stricter, but
        it means reading the file on every request to avoid reading it on every
        request.

        The outlook is in here so that a rebuilt outlook.json on a mounted
        volume is picked up the same way a rebuilt panel is.
        """
        root = self.settings.feature_store
        return (
            _file_id(root / ANNUAL_PANEL if root.is_dir() else root),
            _file_id(self.settings.outlook_artifact),
        )

    def ensure_fresh(self) -> None:
        """Reload or recompute if the panel changed or the model's TTL lapsed.

        Called on the read path, which is what makes a mounted panel usable: the
        file is rebuilt outside the container and the next request picks it up,
        with no API call and no restart. POST /signals/refresh remains for
        forcing it.

        This is also the self-healing path for a container that started
        unready -- fix the mount and the next request loads it.
        """
        with self._lock:
            if self.settings.watch_feature_store:
                current = self._input_fingerprint()
                if current != self._fingerprint:
                    log.info(
                        "panel or outlook changed on disk, reloading",
                        extra={"was": self._fingerprint, "now": current},
                    )
                    signal_recomputes.labels("panel_changed").inc()
                    self.reload()
                    return

            if not self.ready:
                return

            assert self.model is not None and self.store is not None
            ttl = self.model.signal_ttl_s
            if ttl is None or self._computed_at is None:
                return
            age = (datetime.now(timezone.utc) - self._computed_at).total_seconds()
            if age < ttl:
                return

            # The panel is unchanged, so only the cross-section is recomputed --
            # no re-parse of the CSV and no re-load of the artifact.
            signal_recomputes.labels("ttl_expired").inc()
            with tracer.start_as_current_span("model.signals") as span:
                span.set_attribute("recompute.reason", "ttl_expired")
                span.set_attribute("recompute.age_s", round(age, 3))
                self._signals = self.model.signals(self.store)
                span.set_attribute("signals.count", len(self._signals))
            self._computed_at = datetime.now(timezone.utc)
            log.debug(
                "recomputed after ttl",
                extra={"age_s": round(age, 3), "ttl_s": ttl,
                       "signals": len(self._signals)},
            )

    @property
    def ready(self) -> bool:
        return (self.store is not None and self.model is not None
                and self.outlook is not None)

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
        self.ensure_fresh()
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
        self.ensure_fresh()
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

    # -- outlook ---------------------------------------------------------

    def outlook_info(self) -> OutlookInfo:
        self.require_ready()
        assert self.outlook is not None
        o = self.outlook
        return OutlookInfo(
            artifact=str(o.source),
            built_at=o.built_at,
            source_mtime=o.source_mtime,
            inputs=o.inputs,
            national=_model_ref(o.national, o.national_month),
            state=_model_ref(o.state, o.state_month),
        )

    def national_outlook(self) -> NationalOutlook:
        self.ensure_fresh()
        self.require_ready()
        assert self.outlook is not None
        o, row = self.outlook, self.outlook.national_row
        forecast = add_months(row.month, o.national.horizon_months)
        return NationalOutlook(
            built_at=o.built_at,
            model=_model_info(o.national),
            data_through=row.month,
            forecast_month=forecast,
            forecast_month_closed=month_closed(forecast),
            probability=row.probability,
            base_rate=o.national.base_rate,
            intercept=o.national.intercept,
            contributions=_contributions(row),
        )

    def state_outlook(self, top: int | None = None) -> StateOutlook:
        """States ranked by probability, highest first; `top` keeps the first N."""
        self.ensure_fresh()
        self.require_ready()
        assert self.outlook is not None
        o = self.outlook
        rows = o.state_rows if top is None else o.state_rows[:top]
        forecast = add_months(o.state_month, o.state.horizon_months)
        return StateOutlook(
            built_at=o.built_at,
            model=_model_info(o.state),
            data_through=o.state_month,
            forecast_month=forecast,
            forecast_month_closed=month_closed(forecast),
            base_rate=o.state.base_rate,
            intercept=o.state.intercept,
            count=len(rows),
            states=[
                StateOutlookEntry(
                    state=row.state or "",
                    rank=rank,
                    probability=row.probability,
                    contributions=_contributions(row),
                )
                for rank, row in enumerate(rows, start=1)
            ],
        )

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


def _file_id(path: Path) -> _FileId:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _model_ref(model: LogitModel, month) -> OutlookModelRef:
    return OutlookModelRef(
        name=model.name,
        version=model.version,
        data_through=month,
        forecast_month=add_months(month, model.horizon_months),
    )


def _model_info(model: LogitModel) -> OutlookModelInfo:
    return OutlookModelInfo(
        name=model.name,
        version=model.version,
        description=model.description,
        target=model.target,
        horizon_months=model.horizon_months,
        features=list(model.features),
        training=model.training,
        evaluation=model.evaluation,
        notes=list(model.notes),
    )


def _contributions(row: Scored) -> list[Contribution]:
    return [
        Contribution(
            feature=c.feature,
            description=c.description,
            value=c.value,
            standardized=c.standardized,
            coefficient=c.coefficient,
            contribution=c.contribution,
        )
        for c in row.contributions
    ]


class ServiceNotReady(RuntimeError):
    """Raised when a signal endpoint is hit before the model/panel loaded."""
