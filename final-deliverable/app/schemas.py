"""The wire contract.

These models *are* the deliverable's public interface -- the thing other
software is written against -- so they are defined explicitly rather than
serialised ad hoc from internal dataclasses. Renaming a field here is a breaking
change for every consumer; renaming one in features.py is not.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Direction = Literal["expand", "replace", "contract"]


class ModelInfo(BaseModel):
    """Which model produced a signal set, and what its numbers mean."""

    name: str
    version: str
    description: str
    score_units: str = Field(
        description="How to read `score`. Consumers should branch on `direction` "
                    "unless they understand these units."
    )
    required_features: list[str]
    artifact: str | None = Field(
        default=None,
        description="Path to the fitted artifact inside the container, or null "
                    "when the built-in null baseline is being served.",
    )
    is_baseline: bool = Field(
        description="True when no fitted model is loaded. A consumer that must "
                    "not act on the null baseline should check this."
    )


class FeatureStoreInfo(BaseModel):
    """Provenance of the data the signals were computed from."""

    source: str
    rows: int
    companies: int
    periods: int
    latest_period: date
    loaded_at: datetime
    source_mtime: datetime | None


class Signal(BaseModel):
    """One company's signal."""

    nse_symbol: str
    company: str
    tier: str
    score: float
    score_units: str
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    basis: dict[str, float | int | str | None] = Field(
        default_factory=dict,
        description="The inputs behind `score`, so a consumer can audit a signal "
                    "without re-reading the panel.",
    )
    coverage: list[str] = Field(
        default_factory=list,
        description="Which independent-variable series were available for this "
                    "company-period (production / own_reg / own_prod).",
    )
    notes: list[str] = Field(default_factory=list)


class SignalSet(BaseModel):
    """A full cross-section: every company the model could score."""

    as_of: datetime
    horizon: str = Field(
        description="Fiscal period the signals speak to. Advisory metadata -- the "
                    "baseline is cumulative and not horizon-specific."
    )
    model: ModelInfo
    feature_store: FeatureStoreInfo
    count: int
    signals: list[Signal]


class Contribution(BaseModel):
    """One feature's share of an outlook probability."""

    feature: str
    description: str
    value: float = Field(description="The feature as built, in its own units.")
    standardized: float = Field(description="`value` standardised on the training rows.")
    coefficient: float
    contribution: float = Field(
        description="coefficient x standardized, in log-odds. The intercept plus "
                    "every contribution is the logit of `probability`."
    )


class OutlookModelInfo(BaseModel):
    """Which fitted model produced an outlook, and how well it tested."""

    name: str
    version: str = Field(description="Spec version, plus the data month it was refit on.")
    description: str
    target: str = Field(description="Which announcements count: `all` is every one.")
    horizon_months: int
    features: list[str]
    training: dict[str, float | int | str | None]
    evaluation: dict[str, float | int | str | None] = Field(
        description="Out-of-sample scores, re-run by the build on the data the "
                    "model was refit on."
    )
    notes: list[str] = Field(description="Caveats that travel with the numbers.")


class NationalOutlook(BaseModel):
    """P(at least one manufacturing-investment announcement in `forecast_month`)."""

    built_at: datetime
    model: OutlookModelInfo
    data_through: date = Field(description="Latest month of data the forecast reads.")
    forecast_month: date
    forecast_month_closed: bool = Field(
        description="True once forecast_month has ended. The data lags the "
                    "calendar, so this is often true; the forecast is then of a "
                    "month whose outcome may already be public."
    )
    probability: float = Field(ge=0.0, le=1.0)
    base_rate: float = Field(description="Share of training months with an announcement.")
    intercept: float
    contributions: list[Contribution] = Field(description="Largest effect first.")


class StateOutlookEntry(BaseModel):
    state: str
    rank: int = Field(ge=1)
    probability: float = Field(ge=0.0, le=1.0)
    contributions: list[Contribution]


class StateOutlook(BaseModel):
    """States ranked by P(named in an announcement in `forecast_month`).

    The rank is the signal; the level is not well calibrated on so few events.
    """

    built_at: datetime
    model: OutlookModelInfo
    data_through: date
    forecast_month: date
    forecast_month_closed: bool
    base_rate: float
    intercept: float
    count: int
    states: list[StateOutlookEntry]


class OutlookModelRef(BaseModel):
    name: str
    version: str
    data_through: date
    forecast_month: date


class OutlookInfo(BaseModel):
    """Provenance of the outlook artifact being served."""

    artifact: str
    built_at: datetime
    source_mtime: datetime
    inputs: dict[str, str] = Field(description="sha256 of each data/clean input.")
    national: OutlookModelRef
    state: OutlookModelRef


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class Ready(BaseModel):
    status: Literal["ready", "not_ready"]
    model_loaded: bool
    feature_store_loaded: bool
    outlook_loaded: bool
    detail: str | None = None


class Endpoint(BaseModel):
    path: str
    method: str
    summary: str


class Metadata(BaseModel):
    """Everything a consumer needs to integrate, from one call."""

    service: str
    version: str
    horizon: str
    model: ModelInfo
    feature_store: FeatureStoreInfo
    outlook: OutlookInfo
    stream_interval_s: float
    auth_required: bool
    tracing: bool = Field(
        description="Whether spans are being exported. When false, a request's "
                    "X-Request-ID is the only correlation handle.",
    )
    tiers: list[str]
    companies: list[str]
    endpoints: list[Endpoint]


class RefreshResult(BaseModel):
    status: Literal["refreshed"]
    feature_store: FeatureStoreInfo
    model: ModelInfo
    outlook: OutlookInfo
    signals: int


class ErrorDetail(BaseModel):
    detail: str
