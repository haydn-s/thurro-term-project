"""Load the four cleaned files from data/clean/.

Nothing here changes the data; it only reads it with the right types.
Run `python scripts/build_clean_pipeline.py` first if data/clean/ is missing.
"""
import pandas as pd

from config import CLEAN


def load_announcements():
    """One row per investment announcement.

    Rows dated only to a fiscal year (date_precision == "fiscal_period") have no
    month. They are kept here; the monthly code drops them and the annual state
    model uses them.
    """
    a = pd.read_csv(CLEAN / "announcements_clean.csv")
    a["month"] = pd.to_datetime(a["month"])
    return a


def load_production():
    """SIAM production, one row per month x OEM x model.

    `category` is 2W / 3W / Passenger Vehicles. (`segment` is the finer body type,
    e.g. Scooters.)
    """
    p = pd.read_csv(CLEAN / "production_model_monthly.csv", parse_dates=["month"])
    for col in ["production_units", "domestic_sales_units", "export_units"]:
        p[col] = p[col].fillna(0)
    return p


def load_registrations_segment():
    """VAHAN EV registrations, one row per month x vehicle segment (2W, 3W, 4W, ...)."""
    return pd.read_csv(CLEAN / "registrations_segment_monthly.csv", parse_dates=["month"])


def load_registrations_state():
    """VAHAN EV registrations, one row per state x month, one column per segment."""
    return pd.read_csv(CLEAN / "registrations_state_monthly.csv", parse_dates=["month"])
