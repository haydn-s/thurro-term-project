"""The model seam.

Everything above this module talks to a `SignalModel` and knows nothing about
how a signal is produced. Everything below it is replaceable. That boundary is
the whole point of the scaffold: the fitted model is not written yet, so the
container ships a baseline that implements the same protocol and is swapped out
by pointing `MODEL_ARTIFACT` at an artifact once there is one.

The baseline is not a placeholder returning zeros. It emits `CapexIntensityBaseline`
-- the one well-powered quantity the project has actually established, from
`notebook-590/03_capex_panel_eda.ipynb` section 11 -- so the service is end-to-end
testable today, and so the fitted model has a null to beat rather than a blank
page. See ../README.md, "Dropping the real model in".
"""
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from .features import CompanyPeriod, FeatureStore


class ModelArtifactError(RuntimeError):
    """Raised when MODEL_ARTIFACT is set but cannot be turned into a model.

    This is deliberately fatal rather than a fallback to the baseline. An
    operator who sets MODEL_ARTIFACT has stated that the fitted model is what
    should be served; quietly serving the null baseline instead would look
    identical from the outside and would be discovered only in the results.
    """


@dataclass(frozen=True)
class RawSignal:
    """One company's signal, as the model produces it.

    `score` is model-native and its meaning travels in the model's own
    `score_units` -- consumers should read `/metadata` rather than assume a
    scale. `direction` is the discretised form, which is what most downstream
    software will actually branch on.
    """

    nse_symbol: str
    company: str
    tier: str
    score: float
    score_units: str
    direction: str
    confidence: float
    basis: dict[str, float | int | str | None] = field(default_factory=dict)
    coverage: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@runtime_checkable
class SignalModel(Protocol):
    """What the service requires of a model.

    A fitted model satisfies this by implementing `signals()`; it does not need
    to subclass anything. `required_features` is advertised on `/metadata` so a
    consumer can see which panel columns a given model version depends on.
    """

    name: str
    version: str
    description: str
    score_units: str
    required_features: tuple[str, ...]

    #: How long this model's output stays valid, in seconds, or None when the
    #: output is a pure function of the panel.
    #:
    #: The service caches the cross-section and recomputes it when the panel
    #: changes on disk. That is sufficient for a model whose signals move only
    #: when its inputs do. A model that is also a function of *time* -- a decay
    #: term, a rolling window anchored to today, anything reading the clock --
    #: must declare a TTL, or it will serve its first answer forever.
    signal_ttl_s: float | None

    def signals(self, store: FeatureStore) -> list[RawSignal]:
        """Score every company the store can support, skipping those it cannot."""
        ...


class CapexIntensityBaseline:
    """Cumulative capex intensity per company: sum(capex) / sum(depreciation).

    This reproduces the cross-sectional test in notebook 03 section 11, which is
    the project's only well-powered specification: 35 firms, no time dimension to
    run out of. Intensity above 1.0 means a firm is spending more on plant than
    it is writing off, i.e. expanding capacity rather than replacing it.

    What this model is for
    ----------------------
    It carries **no EV information whatsoever**. That is the finding it encodes:
    the notebook measured intensity at 2.06 for EV-led and battery names against
    2.08 for components and ICE-led ones (t = -0.06, n = 35), and an ICE-only
    negative control moved with the EV names. FY23-FY26 automotive capex looks
    like a sector-wide cycle, not an EV-volume response.

    So this is the null a fitted model has to beat. Served on its own it is a
    descriptive signal -- "how hard is this firm expanding, relative to its
    peers" -- which is genuinely useful to a downstream consumer and is honest
    about not answering the project's causal question.
    """

    name = "capex-intensity-baseline"
    version = "0.1.0"
    description = (
        "Cumulative capex / cumulative depreciation per company over its panel "
        "history. The sector-cycle null from notebook 03 s11; contains no EV "
        "features by construction."
    )
    score_units = "ratio_capex_to_depreciation"
    required_features = ("capex_cr", "depreciation_cr")

    #: None, and correctly so: the intensity ratio is cumulative over a filed
    #: panel and reads no clock, so its output changes only when the panel does
    #: -- which the service already watches for. A fitted model should think
    #: about this rather than copy it.
    signal_ttl_s = None

    #: Notebook 03 s11 requires at least three filed years and positive
    #: depreciation before a firm's intensity is read. Both guards matter: a
    #: one-year ratio is a single filing, and a non-positive denominator makes
    #: the ratio meaningless rather than large.
    MIN_YEARS = 3
    #: FY23-FY26 is four filed years, so four is full coverage.
    FULL_YEARS = 4

    #: Intensity is a ratio against replacement, so the thresholds sit around
    #: 1.0, not around the sector mean of ~2.07. A firm at 1.3 is expanding, and
    #: separately is well below its peers -- `basis.sector_median` carries that.
    EXPAND_ABOVE = 1.25
    CONTRACT_BELOW = 0.75

    def signals(self, store: FeatureStore) -> list[RawSignal]:
        per_company = store.by_company()

        intensities: dict[str, tuple[float, int, float, float, CompanyPeriod]] = {}
        for symbol, rows in per_company.items():
            usable = [
                r for r in rows if r.capex_cr is not None and r.depreciation_cr is not None
            ]
            if len(usable) < self.MIN_YEARS:
                continue
            capex = sum(r.capex_cr for r in usable)
            dep = sum(r.depreciation_cr for r in usable)
            if dep <= 0:
                continue
            intensities[symbol] = (capex / dep, len(usable), capex, dep, usable[-1])

        if not intensities:
            return []

        sector_median = statistics.median(v[0] for v in intensities.values())

        out: list[RawSignal] = []
        for symbol, (intensity, years, capex, dep, latest) in sorted(intensities.items()):
            out.append(
                RawSignal(
                    nse_symbol=symbol,
                    company=latest.company,
                    tier=latest.tier,
                    score=round(intensity, 4),
                    score_units=self.score_units,
                    direction=self._direction(intensity),
                    confidence=self._confidence(years),
                    basis={
                        "cumulative_capex_cr": round(capex, 2),
                        "cumulative_depreciation_cr": round(dep, 2),
                        "filed_years": years,
                        "sector_median_intensity": round(sector_median, 4),
                        "vs_sector_median": round(intensity - sector_median, 4),
                        "latest_fiscal_period": latest.fiscal_period,
                        "latest_period_end": latest.period_end.isoformat(),
                    },
                    coverage=latest.x_coverage,
                    notes=(
                        "Baseline carries no EV features; see model.description.",
                    ),
                )
            )
        return out

    def _direction(self, intensity: float) -> str:
        if intensity >= self.EXPAND_ABOVE:
            return "expand"
        if intensity < self.CONTRACT_BELOW:
            return "contract"
        return "replace"

    def _confidence(self, years: int) -> float:
        """Share of the FY23-FY26 window the firm actually filed.

        This is a **data-coverage proxy, not a calibrated probability** and must
        not be read as confidence in the EV hypothesis -- the baseline does not
        test it. A fitted model should replace this with something defensible
        (a prediction interval, a bootstrap spread) and say so in `/metadata`.
        """
        return round(min(years, self.FULL_YEARS) / self.FULL_YEARS, 3)


def load_model(artifact: Path | None) -> SignalModel:
    """Return the model to serve.

    No artifact configured -> the null baseline, which always loads. An artifact
    configured -> that artifact, or a hard failure. There is no third branch; see
    `ModelArtifactError`.
    """
    if artifact is None:
        return CapexIntensityBaseline()
    return _load_artifact(artifact)


def _load_artifact(artifact: Path) -> SignalModel:
    """Deserialise a fitted model. **This is the seam to implement.**

    When the fitted model lands:

      1. add its runtime dependencies to final-deliverable/requirements.txt
         (joblib/scikit-learn, statsmodels, whatever it needs);
      2. implement this function to load `artifact` and return an object
         satisfying `SignalModel` -- name, version, description, score_units,
         required_features, signals();
      3. bake the artifact into the image, or mount it and set MODEL_ARTIFACT;
      4. extend tests/test_model.py with the protocol check that already covers
         the baseline.

    Keeping this a loud failure rather than a stub that returns the baseline is
    what makes step 3 impossible to get silently wrong.
    """
    if not artifact.exists():
        raise ModelArtifactError(
            f"MODEL_ARTIFACT={artifact} does not exist inside the container. "
            f"Bake it into the image or mount it, e.g. "
            f"-v /host/model.joblib:/app/model/model.joblib"
        )
    raise ModelArtifactError(
        f"MODEL_ARTIFACT={artifact} was found but no loader is implemented yet. "
        f"Implement app/model.py::_load_artifact -- see model/README.md for the "
        f"artifact contract. Unset MODEL_ARTIFACT to serve the "
        f"{CapexIntensityBaseline.name} null baseline."
    )
