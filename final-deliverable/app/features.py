"""The feature store: typed access to the modelling panel the container ships.

The serving path reads the same CSVs that `scripts/build_panel.py` writes in the
repo root -- not a re-derivation of them. That is on purpose. If the service
computed its own features it would become a second implementation of the panel
logic, and the two would drift. The build pipeline stays the single source of
truth; this module only reads, types and indexes.

Deliberately standard-library only. `scripts/` in the repo root is stdlib-only
for the same reason, and keeping pandas out of the serving image costs nothing
here (the panel is 182 rows) while removing a large dependency from the
deployed surface. The fitted model may well need numpy/scikit-learn -- add
those to requirements.txt when it lands, not before.
"""
import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

#: Filename the annual panel is expected under inside FEATURE_STORE.
ANNUAL_PANEL = "panel_company_annual.csv"

class FeatureStoreError(RuntimeError):
    """Raised when the panel is missing, unreadable or missing columns."""


def _opt_float(raw: str | None) -> float | None:
    """Parse a panel cell to float, mapping blanks to None.

    The panel uses an empty cell for "not available" in several distinct senses
    -- no prior period to difference against, no own-volume series for this
    maker, window not covered by the source. None preserves that; coercing to
    0.0 would quietly turn "unknown" into "no growth" and bias every aggregate
    that touches it.
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise FeatureStoreError(f"non-numeric panel value: {raw!r}") from exc


def _opt_int(raw: str | None) -> int | None:
    value = _opt_float(raw)
    return None if value is None else int(value)


@dataclass(frozen=True)
class CompanyPeriod:
    """One row of the annual panel: a company's fiscal period.

    Field names match the CSV header except `capex_growth_pct`, which drops the
    panel's `capex_cr_` prefix because the unit (a percentage) contradicts it.
    """

    company: str
    nse_symbol: str
    tier: str
    primary_panel: bool
    fiscal_period: str
    period_end: date
    window_start: str
    window_end: str
    window_months: int | None
    capex_cr: float | None
    capex_growth_pct: float | None
    depreciation_cr: float | None
    cfo_cr: float | None
    national_ev_production: int | None
    national_ev_registrations: int | None
    own_ev_production: int | None
    own_ev_prod_growth_pct: float | None
    own_ev_registrations: int | None
    own_ev_reg_growth_pct: float | None
    asset_formation_cr: float | None
    x_coverage: tuple[str, ...] = field(default=())

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "CompanyPeriod":
        try:
            period_end = datetime.strptime(row["period_end"], "%Y-%m-%d").date()
        except (KeyError, ValueError) as exc:
            raise FeatureStoreError(
                f"bad period_end in panel row {row.get('nse_symbol')!r}: "
                f"{row.get('period_end')!r}"
            ) from exc

        coverage = tuple(
            part for part in row.get("x_coverage", "").split(";") if part.strip()
        )
        return cls(
            company=row["company"],
            nse_symbol=row["nse_symbol"],
            tier=row["tier"],
            primary_panel=row.get("primary_panel", "").strip().lower() == "yes",
            fiscal_period=row["fiscal_period"],
            period_end=period_end,
            window_start=row.get("window_start", ""),
            window_end=row.get("window_end", ""),
            window_months=_opt_int(row.get("window_months")),
            capex_cr=_opt_float(row.get("capex_cr")),
            capex_growth_pct=_opt_float(row.get("capex_cr_growth_pct")),
            depreciation_cr=_opt_float(row.get("depreciation_cr")),
            cfo_cr=_opt_float(row.get("cfo_cr")),
            national_ev_production=_opt_int(row.get("national_ev_production")),
            national_ev_registrations=_opt_int(row.get("national_ev_registrations")),
            own_ev_production=_opt_int(row.get("own_ev_production")),
            own_ev_prod_growth_pct=_opt_float(row.get("own_ev_prod_growth_pct")),
            own_ev_registrations=_opt_int(row.get("own_ev_registrations")),
            own_ev_reg_growth_pct=_opt_float(row.get("own_ev_reg_growth_pct")),
            asset_formation_cr=_opt_float(row.get("asset_formation_cr")),
            x_coverage=coverage,
        )


#: Columns the annual panel must carry for the service to start. A short list on
#: purpose -- it catches "wrong CSV mounted" without failing the build every time
#: build_panel.py adds a column.
REQUIRED_COLUMNS = frozenset(
    {
        "company",
        "nse_symbol",
        "tier",
        "primary_panel",
        "fiscal_period",
        "period_end",
        "capex_cr",
        "depreciation_cr",
    }
)


@dataclass(frozen=True)
class FeatureStore:
    """An immutable in-memory snapshot of the annual panel.

    Loaded once at startup and replaced wholesale on refresh rather than mutated,
    so a request is always served against one internally consistent snapshot
    even if the mounted file is being rewritten underneath.
    """

    rows: tuple[CompanyPeriod, ...]
    source: Path
    loaded_at: datetime
    source_mtime: datetime | None

    @classmethod
    def load(cls, root: Path) -> "FeatureStore":
        path = root / ANNUAL_PANEL if root.is_dir() else root
        if not path.is_file():
            raise FeatureStoreError(
                f"annual panel not found at {path}. FEATURE_STORE should point at "
                f"the directory holding {ANNUAL_PANEL} (the image bakes it in at "
                f"/app/feature-store)."
            )

        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            header = set(reader.fieldnames or ())
            missing = REQUIRED_COLUMNS - header
            if missing:
                raise FeatureStoreError(
                    f"{path} is missing required columns: {sorted(missing)}"
                )
            rows = tuple(CompanyPeriod.from_row(row) for row in reader)

        if not rows:
            raise FeatureStoreError(f"{path} has a header but no data rows")

        stat = path.stat()
        return cls(
            rows=rows,
            source=path,
            loaded_at=datetime.now(timezone.utc),
            source_mtime=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
        )

    # -- queries ---------------------------------------------------------

    def panel(self, primary_only: bool = True) -> tuple[CompanyPeriod, ...]:
        """Rows in the modelling panel.

        `primary_only` mirrors the panel's own `primary_panel` flag, which marks
        the companies with a usable FY23-FY26 cash-flow history. The excluded
        rows are kept in the file (and so in the store) because they document
        why a named target company is absent, but they must not reach a model.
        """
        if not primary_only:
            return self.rows
        return tuple(r for r in self.rows if r.primary_panel)

    def periods(self) -> tuple[date, ...]:
        return tuple(sorted({r.period_end for r in self.panel()}))

    def latest_period(self) -> date:
        periods = self.periods()
        if not periods:
            raise FeatureStoreError("panel has no rows flagged primary_panel=yes")
        return periods[-1]

    def by_company(self) -> dict[str, tuple[CompanyPeriod, ...]]:
        """Panel rows grouped by NSE symbol, each sorted oldest period first."""
        grouped: dict[str, list[CompanyPeriod]] = {}
        for row in self.panel():
            grouped.setdefault(row.nse_symbol, []).append(row)
        return {
            symbol: tuple(sorted(rows, key=lambda r: r.period_end))
            for symbol, rows in grouped.items()
        }

    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.by_company()))

    def tiers(self) -> tuple[str, ...]:
        return tuple(sorted({r.tier for r in self.panel()}))
