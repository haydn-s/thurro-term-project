"""The outlook: next-month investment-announcement probabilities, national and by state.

Served beside the per-company capex signals, and different in kind. The capex
signal is descriptive and has no EV content; the outlook is the project's
leading indicator -- the two fitted models that model development selected:

  national  P(at least one announcement in the forecast month)
  state     P(a state is named in one), served as a ranking of states

Both are logistic regressions fitted offline by `model/build_outlook.py`, which
builds their features with the exploration study's own code. The artifact it
writes carries the coefficients, the scaler and the latest month's feature
rows; this module only evaluates them. That keeps feature construction in one
place, as features.py does for the panel, and keeps scikit-learn out of the
serving image: a logistic regression is a dot product and a sigmoid.

Every probability the build script stored is recomputed here at load, and a
mismatch is fatal. An artifact that was hand-edited, truncated or written by a
different spec would otherwise serve plausible numbers that no model produced.
"""
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

#: The artifact layout this module reads. build_outlook.py writes the same
#: number; anything else is refused rather than half-read.
SCHEMA_VERSION = 1

#: How far a recomputed probability may sit from the one scikit-learn gave.
#: Both are float64 evaluations of the same expression, so they agree to
#: ~1e-15; this leaves room for summation order, and none for a changed number.
PROBABILITY_TOLERANCE = 1e-9


class OutlookArtifactError(RuntimeError):
    """Raised when the outlook artifact is missing, malformed or inconsistent."""


def add_months(month: date, n: int) -> date:
    index = month.year * 12 + month.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


def month_closed(month: date, today: date | None = None) -> bool:
    """True once `month` has ended -- the forecast is then of a month already past.

    The data runs a month or more behind the calendar, so this is often true:
    the forecast is still the model's answer for that month, and a consumer
    comparing it with what actually happened needs to know which it is reading.
    """
    today = today or datetime.now(timezone.utc).date()
    return today >= add_months(month, 1)


@dataclass(frozen=True)
class Contribution:
    """One feature's share of a prediction, in log-odds."""

    feature: str
    description: str
    value: float
    standardized: float
    coefficient: float
    contribution: float


@dataclass(frozen=True)
class Scored:
    """One scored row: a probability and the contributions that sum to it."""

    month: date
    probability: float
    contributions: tuple[Contribution, ...]
    state: str | None = None


@dataclass(frozen=True)
class LogitModel:
    """A fitted, standardised logistic regression and its provenance."""

    name: str
    version: str
    description: str
    target: str
    horizon_months: int
    features: tuple[str, ...]
    descriptions: dict[str, str]
    mean: tuple[float, ...]
    scale: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    training: dict[str, Any]
    evaluation: dict[str, Any]
    notes: tuple[str, ...]

    @property
    def base_rate(self) -> float:
        return float(self.training["base_rate"])

    def score(self, values: dict[str, float]) -> tuple[float, tuple[Contribution, ...]]:
        """Probability for one feature row, with each feature's contribution.

        Contributions are sorted largest effect first, which is the order a
        reader wants: what pushed this month's probability up or down most.
        """
        parts = []
        for feature, mean, scale, coef in zip(
            self.features, self.mean, self.scale, self.coefficients
        ):
            z = (values[feature] - mean) / scale
            parts.append(Contribution(
                feature=feature,
                description=self.descriptions.get(feature, ""),
                value=values[feature],
                standardized=z,
                coefficient=coef,
                contribution=coef * z,
            ))
        logit = self.intercept + math.fsum(p.contribution for p in parts)
        return _sigmoid(logit), tuple(sorted(parts, key=lambda p: -abs(p.contribution)))


def _sigmoid(x: float) -> float:
    # Split on sign so a large |x| cannot overflow exp().
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


@dataclass(frozen=True)
class Outlook:
    """An immutable snapshot of the outlook artifact, verified at load."""

    source: Path
    source_mtime: datetime
    built_at: datetime
    inputs: dict[str, str]
    national: LogitModel
    national_row: Scored
    state: LogitModel
    #: Highest probability first; the rank is the position.
    state_rows: tuple[Scored, ...]

    @classmethod
    def load(cls, path: Path) -> "Outlook":
        if not path.is_file():
            raise OutlookArtifactError(
                f"outlook artifact not found at {path}. OUTLOOK_ARTIFACT should "
                f"point at the outlook.json written by model/build_outlook.py "
                f"(the image bakes it in at /app/model/outlook.json)."
            )
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise OutlookArtifactError(f"cannot read {path}: {exc}") from exc

        try:
            if raw.get("schema_version") != SCHEMA_VERSION:
                raise OutlookArtifactError(
                    f"{path} has schema_version {raw.get('schema_version')!r}; this "
                    f"service reads {SCHEMA_VERSION}. Rebuild it with "
                    f"model/build_outlook.py from the same commit as the service."
                )
            national = _model(raw["national"])
            state = _model(raw["state"])
            national_rows = _scored(national, raw["national"]["scored"], keyed=False)
            state_rows = _scored(state, raw["state"]["scored"], keyed=True)
            built_at = datetime.fromisoformat(raw["built_at"])
            inputs = dict(raw["inputs"])
        except OutlookArtifactError as exc:
            raise OutlookArtifactError(f"{path}: {exc}") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise OutlookArtifactError(f"{path} is malformed: {exc!r}") from exc

        if len(national_rows) != 1:
            raise OutlookArtifactError(
                f"{path}: expected one national row, found {len(national_rows)}"
            )
        if not state_rows:
            raise OutlookArtifactError(f"{path}: no state rows to rank")
        if len({r.month for r in state_rows}) != 1:
            raise OutlookArtifactError(f"{path}: state rows span more than one month")

        return cls(
            source=path,
            source_mtime=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc),
            built_at=built_at,
            inputs=inputs,
            national=national,
            national_row=national_rows[0],
            state=state,
            state_rows=tuple(sorted(state_rows, key=lambda r: (-r.probability, r.state))),
        )

    @property
    def national_month(self) -> date:
        return self.national_row.month

    @property
    def state_month(self) -> date:
        return self.state_rows[0].month


def _model(section: dict[str, Any]) -> LogitModel:
    features = tuple(section["features"])
    vectors = {k: tuple(float(v) for v in section[k])
               for k in ("scaler_mean", "scaler_scale", "coefficients")}
    for name, vector in vectors.items():
        if len(vector) != len(features):
            raise OutlookArtifactError(
                f"{section['name']}: {name} has {len(vector)} entries for "
                f"{len(features)} features"
            )
        if not all(math.isfinite(v) for v in vector):
            raise OutlookArtifactError(f"{section['name']}: {name} is not finite")
    if any(s <= 0 for s in vectors["scaler_scale"]):
        raise OutlookArtifactError(f"{section['name']}: a scaler_scale is not positive")
    return LogitModel(
        name=section["name"],
        version=section["version"],
        description=section["description"],
        target=section["target"],
        horizon_months=int(section["horizon_months"]),
        features=features,
        descriptions=dict(section.get("descriptions", {})),
        mean=vectors["scaler_mean"],
        scale=vectors["scaler_scale"],
        coefficients=vectors["coefficients"],
        intercept=float(section["intercept"]),
        training=dict(section["training"]),
        evaluation=dict(section["evaluation"]),
        notes=tuple(section.get("notes", ())),
    )


def _scored(model: LogitModel, rows: list[dict[str, Any]], keyed: bool) -> list[Scored]:
    out = []
    for row in rows:
        label = row.get("state") if keyed else "national"
        missing = set(model.features) - set(row["features"])
        if missing:
            raise OutlookArtifactError(f"{model.name}, {label}: missing {sorted(missing)}")
        values = {f: float(row["features"][f]) for f in model.features}
        if not all(math.isfinite(v) for v in values.values()):
            raise OutlookArtifactError(f"{model.name}, {label}: a feature is not finite")
        probability, contributions = model.score(values)
        stored = float(row["probability"])
        if abs(probability - stored) > PROBABILITY_TOLERANCE:
            raise OutlookArtifactError(
                f"{model.name}, {label}: recomputed probability {probability!r} does "
                f"not match the stored {stored!r}. The coefficients, scaler or "
                f"features were changed after the build; rebuild the artifact "
                f"rather than editing it."
            )
        out.append(Scored(
            month=date.fromisoformat(row["month"]),
            probability=probability,
            contributions=contributions,
            state=row["state"] if keyed else None,
        ))
    return out
