"""Checks for the exploration package.

Run from the repo root:
    pytest final-deliverable/model/exploration -q

The most important test is the leakage one: changing what happens in the future
must not change any earlier prediction.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
import pytest

import feature_engineering as fe
from evaluation import walk_forward
from models import NATIONAL_MODELS


@pytest.fixture(scope="module")
def nat():
    return fe.national_features()


@pytest.fixture(scope="module")
def state():
    return fe.state_features(horizon=1)


def test_features_have_no_gaps(nat):
    cols = fe.feature_sets("all")["all"]
    assert nat[cols].isna().sum().sum() == 0


def test_target_is_next_month(nat):
    # y for month t must equal the announcement count in month t+1
    nxt = nat["events_now_all"].shift(-1)
    both = nat["y_count_all_h1"].notna() & nxt.notna()
    assert (nat.loc[both, "y_count_all_h1"] == nxt[both]).all()


def test_h3_target_is_sum_of_next_three(nat):
    s = nat["events_now_all"]
    expected = s.shift(-1) + s.shift(-2) + s.shift(-3)
    both = expected.notna()
    assert (nat.loc[both, "y_count_all_h3"] == expected[both]).all()


def test_features_use_only_the_past(nat):
    # prod_vs_6m_max divides by the max of the PREVIOUS 6 months, never including t
    p = nat["prod_total"]
    i = 10
    manual = p.iloc[i] / fe.load_production().groupby("month")["production_units"].sum() \
        .sort_index().loc[:nat["month"].iloc[i]].iloc[-7:-1].max()
    assert nat["prod_vs_6m_max"].iloc[i] == pytest.approx(manual)


@pytest.mark.parametrize("name", ["Poisson, core", "Logit L2, core", "Random forest, all"])
@pytest.mark.parametrize("h", [1, 3])
def test_walk_forward_does_not_leak(nat, name, h):
    spec = NATIONAL_MODELS[name]
    feats = fe.CORE_FEATURES if "core" in name else fe.feature_sets("all")["all"]
    y_any, y_count = f"y_any_all_h{h}", f"y_count_all_h{h}"
    first_test = 16
    real = walk_forward(nat, feats, y_any, y_count, spec, first_test, h)

    # scramble every outcome from row `cut` onward; predictions for months before
    # `cut` must not move, because those outcomes were not known yet
    cut = 24
    fake = nat.copy()
    rng = np.random.default_rng(1)
    fake.loc[cut:, y_count] = rng.integers(0, 4, len(fake) - cut).astype(float)
    fake.loc[cut:, y_any] = (fake.loc[cut:, y_count] > 0).astype(float)
    unknown = nat[y_any].isna()                 # keep months with no outcome as unknown
    fake.loc[unknown, [y_any, y_count]] = np.nan
    moved = walk_forward(fake, feats, y_any, y_count, spec, first_test, h)
    cut_month = nat["month"].iloc[cut]
    a = real[real["month"] < cut_month]["p"].to_numpy()
    b = moved[moved["month"] < cut_month]["p"].to_numpy()
    assert len(a) > 0 and np.allclose(a, b)


def test_state_shares_sum_to_one(state):
    sums = state.groupby("month")["share_total"].sum()
    assert np.allclose(sums, 1.0)


def test_state_target_known_case(state):
    # Maharashtra had an announcement in Dec 2023, so its Nov 2023 row is a positive
    row = state[(state["state"] == "Maharashtra") & (state["month"] == "2023-11-01")]
    assert row["y_any"].iloc[0] == 1


def test_fiscal_year_mapping():
    m = pd.Series(pd.to_datetime(["2025-03-01", "2025-04-01", "2026-03-01"]))
    assert list(fe.fiscal_year(m)) == [2025, 2026, 2026]


def test_fiscal_year_table_counts_undated_rows():
    fy = fe.state_fiscal_year()
    ann = fe.load_announcements().dropna(subset=["state"])
    assert fy["announcements"].sum() == len(ann[ann["announcement_date"].str[:2] != "FY"]) \
        + len(ann[ann["announcement_date"].str[:2] == "FY"]) - _outside_window(ann)


def _outside_window(ann):
    # announcements whose fiscal year falls outside FY2023-FY2027
    dated = ann.dropna(subset=["month"])
    fy = fe.fiscal_year(dated["month"])
    return int((~fy.between(2023, 2027)).sum())
