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


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class Ready(BaseModel):
    status: Literal["ready", "not_ready"]
    model_loaded: bool
    feature_store_loaded: bool
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
    signals: int


class ErrorDetail(BaseModel):
    detail: str
