"""Track C: sequence models on state EV registrations, 1 to 6 months ahead.

Track B's question, asked of a different model class. A feedforward network on
21 engineered lags lost to the random walk; this tests whether that was the
network or the lags, by giving GRU, LSTM, TCN, Transformer and N-BEATS models
the raw monthly window instead and letting them learn their own summary.

Same panel, same 34 states, same train/test cut and the same rows as Track B,
so its one-month-ahead numbers sit in the same table. Added on top:

* **Horizons 1-6.** A random walk is hardest to beat one month out. If there is
  structure a network can use (seasonality, cross-state co-movement), the
  longer horizons are where it should show.
* **Quantiles.** Every model predicts the 10th, 50th and 90th percentile, scored
  for coverage against intervals the simple baselines build from their own
  training errors.
* **Exponential smoothing** as a baseline, which turned out to be the one to beat.
* **A control** -- Track B's MLP on Track B's features, trained by this harness --
  to separate how a network is trained from what it is shown.
* **SES hybrids** -- each network predicting the residual over the SES forecast.
* **A rolling-origin backtest** of the deciding comparison, refitting every six
  months from 2022-09, because the hybrids were added after a first look at the
  main test window.

Protocol, fixed before any test month was scored
------------------------------------------------
1. Inner validation: the last 12 months of training origins. Each architecture
   x seed x window length is trained on the months before them and early-stopped
   on them.
2. Window length is chosen per architecture by mean validation loss over seeds.
3. Each seed is refitted on the whole training window for its own best epoch
   count, and predicts the test months once.

The test months are touched only in step 3, and only for scoring. Nothing here
is chosen on them, including which architecture the per-state breakdown uses
(lowest validation loss).

Leakage
-------
A sample's window ends at its origin month t and its targets are months t+h. A
training target may not fall after the first test origin, and an inner-training
target may not fall after the first validation origin; both are enforced by
masks, not by trusting the row order. Scalers are fitted on training windows
only. test_seq.py asserts each of these.
"""
import warnings

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import nn_volume as nv
from nn_config import (N_SEEDS, RANDOM_STATE, RESULTS, SEQ_BATCH, SEQ_HORIZON,
                       SEQ_MAJOR_STATE_MIN_MONTHLY, SEQ_MAX_EPOCHS, SEQ_N_JOBS,
                       SEQ_PATIENCE, SEQ_QUANTILES, SEQ_REPORT_HORIZONS,
                       SEQ_ROLLING_ARCHS, SEQ_ROLLING_BLOCK, SEQ_ROLLING_ORIGINS,
                       SEQ_ROLLING_WINDOW, SEQ_VAL_MONTHS, SEQ_WINDOWS,
                       VOLUME_MAX_LOOKBACK, VOLUME_TRAIN_END)
from nn_models import reg_mlp_small, ridge, seed_list

from config import N_BOOTSTRAP   # the shared study's bootstrap size

warnings.filterwarnings("ignore")

# Per-month channels. `present` must stay last: the models read it as the mask.
CHANNELS = ["rel_level", "dlog", "share_2w", "share_3w", "share_4w",
            "nat_dlog", "month_sin", "month_cos", "present"]
UNSCALED = {"month_sin", "month_cos", "present"}
STATIC = ["anchor_level"]

ARCH_NAMES = ["GRU", "LSTM", "TCN", "Transformer", "N-BEATS"]

# Trained by the same harness but reading Track B's 21 features instead of the
# window, so the comparison separates "how the network was trained" from "what
# it was shown". See seq_models.FeatureMLP.
CONTROL_ARCHS = ["MLP (16), Track C training"]

# ES-RNN-style hybrids (Smyl 2020, the M4 winner): the same five networks,
# predicting the residual over the SES forecast instead of over "no change".
# With the head's zero start an untrained hybrid is exactly SES, so the network
# has to earn every departure from the smoother -- the direct test of whether a
# network adds anything to what smoothing already finds.
HYBRID = " on SES"
HYBRID_ARCHS = [a + HYBRID for a in ARCH_NAMES]

ALL_ARCHS = ARCH_NAMES + HYBRID_ARCHS + CONTROL_ARCHS


def base_arch(name):
    """The network a model name trains: 'GRU on SES' trains a GRU."""
    return name.removesuffix(HYBRID)


# =====================================================================
# Panel and samples
# =====================================================================
def seq_panel(full=None):
    """Track B's states on a complete monthly grid, with one row of channels per month.

    Every channel at month m is known at m: the state's own level, change and
    segment mix, the national change in total registrations (summed across all
    36 states, so it does not depend on which states were kept), and the
    calendar.
    """
    full = nv.complete_panel() if full is None else full
    keep = sorted(nv.build_volume_features(full.copy())["state"].unique())

    nat = full.groupby("month")["ev_total"].sum().sort_index()
    nat_dlog = np.log1p(nat).diff().fillna(0.0)

    d = full[full["state"].isin(keep)].copy()
    d = d.sort_values(["state", "month"]).reset_index(drop=True)
    d["log_total"] = np.log1p(d["ev_total"])
    d["dlog"] = d.groupby("state")["log_total"].diff().fillna(0.0)
    total = d["ev_total"].replace(0, np.nan)
    for seg in ("2w", "3w", "4w"):
        d[f"share_{seg}"] = (d[f"ev_{seg}"] / total).fillna(0.0)
    d["nat_dlog"] = d["month"].map(nat_dlog)
    d["month_sin"] = np.sin(2 * np.pi * d["month"].dt.month / 12)
    d["month_cos"] = np.cos(2 * np.pi * d["month"].dt.month / 12)
    return d


def build_samples(p, window, horizon=SEQ_HORIZON, min_history=VOLUME_MAX_LOOKBACK):
    """One sample per (state, origin month t) with `min_history` earlier months.

    min_history = 12 is the condition every Track B row meets (it needs lag12),
    so the one-step samples are exactly Track B's rows.

    Returns arrays x [N, L, C], s [N, 1], idx [N], y [N, H] (NaN past the data),
    and a frame of (state, month, state_idx, log_total) for each sample.
    """
    states = sorted(p["state"].unique())
    xs, ss, ids, ys, meta = [], [], [], [], []
    feat_cols = [c for c in CHANNELS if c not in {"rel_level", "present"}]

    for si, state in enumerate(states):
        g = p[p["state"] == state]
        lvl = g["log_total"].to_numpy()
        feats = g[feat_cols].to_numpy()
        months = g["month"].to_numpy()
        T = len(g)
        for t in range(min_history, T):
            y = np.full(horizon, np.nan)
            ahead = lvl[t + 1:t + 1 + horizon] - lvl[t]
            y[:len(ahead)] = ahead
            if np.isnan(y).all():
                continue                         # the last month has nothing to score

            x = np.zeros((window, len(CHANNELS)))
            lo = max(0, t - window + 1)
            n = t - lo + 1                       # real months in the window
            x[-n:, 0] = lvl[lo:t + 1] - lvl[t]   # rel_level: 0 at the origin
            x[-n:, 1:-1] = feats[lo:t + 1]
            x[-n:, -1] = 1.0                     # present
            xs.append(x)
            ss.append([lvl[t]])
            ids.append(si)
            ys.append(y)
            meta.append((state, months[t], si, lvl[t]))

    meta = pd.DataFrame(meta, columns=["state", "month", "state_idx", "log_total"])
    return {"x": np.asarray(xs, np.float32), "s": np.asarray(ss, np.float32),
            "idx": np.asarray(ids, np.int64), "y": np.asarray(ys, np.float32),
            "meta": meta, "states": states}


def target_month(meta, h):
    return meta["month"] + pd.DateOffset(months=h)


def split_masks(meta, y, train_end=VOLUME_TRAIN_END, val_months=SEQ_VAL_MONTHS,
                test_months=None):
    """Which samples and which of their horizons each phase may use.

    Returns boolean row selectors and [N, H] target masks for: train (all
    training origins), inner_train and val (the inner validation split), and
    test (every later origin, or only the next `test_months` of them).

    A training origin t uses horizon h only if t + h is no later than the first
    test origin -- the latest month whose value is known when the first test
    forecast is made. Without this a 6-month target from a March 2025 origin
    would train on September 2025, which is inside the test window.
    """
    train_end = pd.Timestamp(train_end)
    first_test = train_end + pd.DateOffset(months=1)
    first_val = train_end - pd.DateOffset(months=val_months - 1)
    H = y.shape[1]
    has_y = ~np.isnan(y)
    tm = np.stack([target_month(meta, h).to_numpy() for h in range(1, H + 1)], axis=1)

    origin = meta["month"].to_numpy()
    rows = {
        "train": origin <= np.datetime64(train_end),
        "inner_train": origin < np.datetime64(first_val),
        "val": (origin >= np.datetime64(first_val)) & (origin <= np.datetime64(train_end)),
        "test": origin > np.datetime64(train_end),
    }
    if test_months is not None:
        last = train_end + pd.DateOffset(months=test_months)
        rows["test"] &= origin <= np.datetime64(last)
    masks = {
        "train": has_y & (tm <= np.datetime64(first_test)),
        "inner_train": has_y & (tm <= np.datetime64(first_val)),
        "val": has_y & (tm <= np.datetime64(first_test)),
        "test": has_y,
    }
    out = {}
    for k in rows:
        m = masks[k] & rows[k][:, None]
        out[k] = (rows[k] & m.any(axis=1), m)
    return out


class ChannelScaler:
    """Standardise the sequence and static inputs with training statistics only.

    Padding steps are excluded from the statistics and set back to exactly 0
    afterwards, so "padding" stays one unambiguous value.
    """

    def fit(self, x, s):
        present = x[..., -1] == 1
        self.cols = [i for i, c in enumerate(CHANNELS) if c not in UNSCALED]
        vals = x[present][:, self.cols]
        self.mu, self.sd = vals.mean(0), vals.std(0) + 1e-6
        self.s_mu, self.s_sd = s.mean(0), s.std(0) + 1e-6
        return self

    def transform(self, x, s):
        x = x.copy()
        present = x[..., -1:] == 1
        x[..., self.cols] = (x[..., self.cols] - self.mu) / self.sd
        x = np.where(present, x, 0.0).astype(np.float32)
        return x, ((s - self.s_mu) / self.s_sd).astype(np.float32)


def with_track_b_features(samples):
    """The same samples, with Track B's 21 features as the static vector.

    Only the controls read it; the window is kept so the shapes stay uniform.
    """
    feats = nv.build_volume_features()
    X = samples["meta"][["state", "month"]].merge(
        feats[["state", "month"] + nv.FEATURES], on=["state", "month"], how="left")
    if X[nv.FEATURES].isna().any().any():
        raise ValueError("a sequence sample has no Track B row; the row sets diverged")
    return dict(samples, s=X[nv.FEATURES].to_numpy(np.float32))


def with_ses_offset(samples, p, alpha):
    """The same samples with an `offset`: SES's forecast of every h-month change.

    The smoothed level at t uses months <= t only, and alpha is the one fitted on
    training rows, so the offset is known at the origin. The gap between the
    level and its smoothed value is also appended to the static vector, so the
    models that read it can see how far the smoother is from the last month;
    N-BEATS reads only the window, as before.
    """
    lv = ses_levels(p, alpha)
    meta = samples["meta"]
    gap = (np.array([lv[k] for k in zip(meta["state"], meta["month"])])
           - meta["log_total"].to_numpy())
    return dict(samples,
                s=np.column_stack([samples["s"], gap]).astype(np.float32),
                offset=np.repeat(gap[:, None], SEQ_HORIZON, axis=1).astype(np.float32))


def phase_data(samples, rows, mask, scaler):
    x, s = scaler.transform(samples["x"][rows], samples["s"][rows])
    y = samples["y"][rows]
    if "offset" in samples:              # hybrids learn the residual over SES
        y = y - samples["offset"][rows]
    return {"x": x, "s": s, "idx": samples["idx"][rows],
            "y": np.nan_to_num(y, nan=0.0).astype(np.float32),
            "m": mask[rows].astype(np.float32)}


def predict_changes(model, samples, rows, mask, scaler):
    """[N, H, Q] forecasts of the log change, with a hybrid's SES offset added back."""
    import seq_models as sm
    q = sm.predict(model, phase_data(samples, rows, mask, scaler))
    if "offset" in samples:
        q = q + samples["offset"][rows][..., None]
    return q


# =====================================================================
# Training jobs (run in parallel worker processes)
# =====================================================================
def _dims(samples, window):
    return {"n_channels": len(CHANNELS), "n_static": samples["s"].shape[1],
            "n_states": len(samples["states"]), "horizon": SEQ_HORIZON,
            "quantiles": SEQ_QUANTILES, "window": window}


def _validate_job(arch, seed, window, samples, splits, max_epochs, patience):
    import torch
    import seq_models as sm
    torch.set_num_threads(1)
    tr_rows, tr_mask = splits["inner_train"]
    va_rows, va_mask = splits["val"]
    scaler = ChannelScaler().fit(samples["x"][tr_rows], samples["s"][tr_rows])
    model = sm.build(base_arch(arch), seed, **_dims(samples, window))
    model, best_epoch, best_loss, secs = sm.fit(
        model, phase_data(samples, tr_rows, tr_mask, scaler), SEQ_QUANTILES,
        val=phase_data(samples, va_rows, va_mask, scaler), epochs=max_epochs,
        patience=patience, batch=SEQ_BATCH, seed=seed)
    return {"model": arch, "seed": seed, "window": window, "val_loss": best_loss,
            "best_epoch": best_epoch, "seconds": secs, "params": sm.n_params(model),
            "inner_train_rows": int(tr_rows.sum()), "val_rows": int(va_rows.sum())}


def _refit_job(arch, seed, window, epochs, samples, splits):
    import torch
    import seq_models as sm
    torch.set_num_threads(1)
    tr_rows, tr_mask = splits["train"]
    te_rows, te_mask = splits["test"]
    scaler = ChannelScaler().fit(samples["x"][tr_rows], samples["s"][tr_rows])
    model = sm.build(base_arch(arch), seed, **_dims(samples, window))
    model, _, _, secs = sm.fit(model, phase_data(samples, tr_rows, tr_mask, scaler),
                               SEQ_QUANTILES, epochs=epochs, batch=SEQ_BATCH, seed=seed)
    return {"model": arch, "seed": seed, "window": window, "epochs": epochs,
            "seconds": secs,
            "test": predict_changes(model, samples, te_rows, te_mask, scaler),
            "train": predict_changes(model, samples, tr_rows, tr_mask, scaler)}


def train_sequence_models(p, archs=ALL_ARCHS, n_seeds=N_SEEDS, windows=SEQ_WINDOWS,
                          n_jobs=SEQ_N_JOBS, max_epochs=SEQ_MAX_EPOCHS,
                          patience=SEQ_PATIENCE, train_end=VOLUME_TRAIN_END,
                          test_months=None):
    """Validation sweep, window choice, then refit. Returns (selection, refits, samples).

    `samples` maps each window length to its sample set; their rows are
    identical (padding is the only difference), which test_seq.py checks.
    """
    samples = {w: build_samples(p, w) for w in windows}
    splits = split_masks(samples[windows[0]]["meta"], samples[windows[0]]["y"],
                         train_end=train_end, test_months=test_months)
    seeds = seed_list(n_seeds)
    feature_samples = (with_track_b_features(samples[windows[0]])
                       if any(a in CONTROL_ARCHS for a in archs) else None)
    hybrid_samples = None
    if any(a in HYBRID_ARCHS for a in archs):
        first = samples[windows[0]]
        tr_rows, tr_mask = splits["train"]
        alpha, _ = fit_ses(p, first["meta"], first["y"][:, 0], tr_rows & tr_mask[:, 0])
        hybrid_samples = {w: with_ses_offset(samples[w], p, alpha) for w in windows}

    def inputs(arch, w):
        if arch in CONTROL_ARCHS:
            return feature_samples
        return hybrid_samples[w] if arch in HYBRID_ARCHS else samples[w]

    def windows_for(arch):            # the controls ignore the window
        return windows[:1] if arch in CONTROL_ARCHS else windows

    val = Parallel(n_jobs=n_jobs)(
        delayed(_validate_job)(a, sd, w, inputs(a, w), splits, max_epochs, patience)
        for a in archs for sd in seeds for w in windows_for(a))
    val = pd.DataFrame(val)

    mean_loss = val.groupby(["model", "window"], as_index=False)["val_loss"].mean()
    chosen = mean_loss.loc[mean_loss.groupby("model")["val_loss"].idxmin()]
    chosen = dict(zip(chosen["model"], chosen["window"]))
    val["chosen"] = val.apply(lambda r: chosen[r["model"]] == r["window"], axis=1)

    jobs = val[val["chosen"]]
    refits = Parallel(n_jobs=n_jobs)(
        delayed(_refit_job)(r.model, r.seed, r.window, int(r.best_epoch),
                            inputs(r.model, r.window), splits)
        for r in jobs.itertuples())
    return val, refits, samples, splits


# =====================================================================
# Baselines and reference models
# =====================================================================
def baseline_forecasts(p, samples, splits):
    """Point forecasts [N, H] of the log change, for every sample.

    Naive         no change (the random walk)
    Drift         h x the mean one-month change over training origins, as Track B
    Seasonal      the change a year earlier: level(t+h-12) - level(t)
    SES           simple exponential smoothing of the log level, one alpha for
                  all states, chosen on one-step training errors only
    """
    meta, H = samples["meta"], SEQ_HORIZON
    tr_rows, tr_mask = splits["train"]
    lookup = {(r.state, r.month): r.log_total for r in p.itertuples()}
    out = {"Naive (last month)": np.zeros((len(meta), H))}

    dlog_at_origin = p.set_index(["state", "month"])["dlog"]
    origin_dlog = dlog_at_origin.loc[list(zip(meta["state"], meta["month"]))].to_numpy()
    mu = origin_dlog[tr_rows].mean()
    out["Drift (last + mean growth)"] = np.tile(mu * np.arange(1, H + 1), (len(meta), 1))

    seas = np.full((len(meta), H), np.nan)
    for i, r in enumerate(meta.itertuples()):
        for h in range(1, H + 1):
            past = lookup.get((r.state, r.month + pd.DateOffset(months=h - 12)))
            if past is not None:
                seas[i, h - 1] = past - r.log_total
    out["Seasonal naive (12m)"] = seas

    alpha, levels = fit_ses(p, meta, samples["y"][:, 0], tr_rows & tr_mask[:, 0])
    out["SES"] = np.tile((levels - meta["log_total"].to_numpy())[:, None], (1, H))
    return out, {"ses_alpha": alpha, "drift_per_month": float(mu)}


def ses_levels(p, alpha):
    """Smoothed log level at every state-month, using months <= that month only."""
    lv = {}
    for state, g in p.groupby("state", sort=False):
        level = None
        for m, y in zip(g["month"], g["log_total"]):
            level = y if level is None else alpha * y + (1 - alpha) * level
            lv[(state, m)] = level
    return lv


def fit_ses(p, meta, y1, use, grid=np.round(np.arange(0.05, 1.0001, 0.05), 2)):
    """Pick the one smoothing weight that minimises one-step MAE on training rows."""
    keys = list(zip(meta["state"], meta["month"]))
    base = meta["log_total"].to_numpy()
    best = (np.inf, None, None)
    for a in grid:
        lv = ses_levels(p, a)
        levels = np.array([lv[k] for k in keys])
        mae = np.mean(np.abs(y1[use] - (levels[use] - base[use])))
        if mae < best[0]:
            best = (mae, float(a), levels)
    return best[1], best[2]


def empirical_quantiles(samples, splits, point, recent_months=24):
    """Turn a point forecast [N, H] into an 80% interval from its own past errors.

    The interval is the point forecast plus the per-state 10th and 90th
    percentiles of that forecast's residuals over recent training origins; the
    median is the point forecast itself, so the point score does not move. This
    is how the simple baselines get intervals to compare the networks' against.

    Restricted to the last 24 training months because 2019-2021 small-state
    volatility would make the intervals far wider than the test period needs --
    which makes these stronger baselines, not weaker ones.
    """
    meta, y = samples["meta"], samples["y"]
    tr_rows, tr_mask = splits["train"]
    cutoff = pd.Timestamp(VOLUME_TRAIN_END) - pd.DateOffset(months=recent_months - 1)
    recent = tr_rows & (meta["month"] >= cutoff).to_numpy()
    resid = y - point
    q = np.repeat(point[:, :, None], len(SEQ_QUANTILES), axis=2)
    for si in np.unique(meta["state_idx"]):
        own = (meta["state_idx"] == si).to_numpy()
        for h in range(SEQ_HORIZON):
            r = resid[own & recent & tr_mask[:, h], h]
            q[own, h, 0] += min(np.quantile(r, SEQ_QUANTILES[0]), 0.0)
            q[own, h, -1] += max(np.quantile(r, SEQ_QUANTILES[-1]), 0.0)
    return q


def reference_forecasts(p, samples, splits, n_seeds=N_SEEDS):
    """Track B's Ridge and MLP (16), refit on its own 21 features at each horizon.

    At h=1 this reproduces Track B's numbers exactly (same rows, features, target
    and seeds), which is the check that the two tracks are scoring the same thing.
    """
    feats = nv.build_volume_features()
    meta = samples["meta"]
    X = meta[["state", "month"]].merge(feats[["state", "month"] + nv.FEATURES],
                                       on=["state", "month"], how="left")
    if X[nv.FEATURES].isna().any().any():
        raise ValueError("a sequence sample has no Track B row; the row sets diverged")
    X = X[nv.FEATURES]
    y = samples["y"]
    tr_rows, tr_mask = splits["train"]

    out = {"Ridge (Track B features)": np.full(y.shape, np.nan)}
    mlp = {sd: np.full(y.shape, np.nan) for sd in seed_list(n_seeds)}
    for h in range(SEQ_HORIZON):
        use = tr_rows & tr_mask[:, h]
        out["Ridge (Track B features)"][:, h] = ridge().fit(X[use], y[use, h]).predict(X)
        for sd in mlp:
            mlp[sd][:, h] = reg_mlp_small(seed=sd).fit(X[use], y[use, h]).predict(X)
    return out, mlp


# =====================================================================
# Scoring
# =====================================================================
def coverage(y, q):
    return float(np.mean((y >= q[:, 0]) & (y <= q[:, -1])))


def mean_pinball(y, q):
    qs = np.asarray(SEQ_QUANTILES)
    diff = y[:, None] - q
    return float(np.mean(np.maximum(qs * diff, (qs - 1) * diff)))


def month_bootstrap(err_base, err_model, months, n=N_BOOTSTRAP, seed=RANDOM_STATE):
    """90% interval of MAE(base) - MAE(model), resampling whole test months.

    Months, not rows: the 34 states in a month share that month's shocks, so
    rows are not independent and a row bootstrap would give intervals that are
    too narrow.
    """
    rng = np.random.default_rng(seed)
    codes, uniq = pd.factorize(pd.Series(months))
    k = len(uniq)
    d = err_base - err_model
    sums = np.bincount(codes, weights=d, minlength=k)
    counts = np.bincount(codes, minlength=k)
    draws = rng.integers(0, k, size=(n, k))
    gains = sums[draws].sum(1) / counts[draws].sum(1)
    return {"gain": float(d.mean()), "gain_ci_low": float(np.percentile(gains, 5)),
            "gain_ci_high": float(np.percentile(gains, 95))}


def score_all(samples, splits, point, quant, majors):
    """One row per (model, seed, horizon, subset) on the test samples.

    Each model gets two paired intervals: its gain over the random walk (Track
    B's reference) and over SES, the strongest one-parameter baseline. A model
    that clears the first and not the second has found what smoothing finds.
    """
    te_rows, te_mask = splits["test"]
    meta = samples["meta"][te_rows].reset_index(drop=True)
    y = samples["y"][te_rows]
    m = te_mask[te_rows]
    naive = point["Naive (last month)"][te_rows]
    ses = point["SES"][te_rows]

    rows = []
    for (name, seed, family), pred in _iter_models(point, quant):
        pred_pt = pred[te_rows] if pred.ndim == 2 else pred[:, :, len(SEQ_QUANTILES) // 2]
        pred_q = None if pred.ndim == 2 else pred
        for h in range(1, SEQ_HORIZON + 1):
            for subset in ("all", "major"):
                use = m[:, h - 1].copy()
                if subset == "major":
                    use &= meta["state"].isin(majors).to_numpy()
                use &= ~np.isnan(pred_pt[:, h - 1])
                yt = y[use, h - 1]
                months = meta.loc[use, "month"].to_numpy()
                e_model = np.abs(yt - pred_pt[use, h - 1])
                e_naive = np.abs(yt - naive[use, h - 1])
                e_ses = np.abs(yt - ses[use, h - 1])
                vs_ses = month_bootstrap(e_ses, e_model, months)
                r = {"model": name, "seed": seed, "family": family, "horizon": h,
                     "subset": subset, "n": int(use.sum()),
                     "test_months": int(meta.loc[use, "month"].nunique()),
                     "mae_log": float(e_model.mean()),
                     "mae_naive": float(e_naive.mean()),
                     **month_bootstrap(e_naive, e_model, months),
                     "gain_vs_ses": vs_ses["gain"],
                     "ses_ci_low": vs_ses["gain_ci_low"],
                     "ses_ci_high": vs_ses["gain_ci_high"],
                     # how much of the forecast is the smoother's forecast
                     "corr_with_ses": float(np.corrcoef(pred_pt[use, h - 1], ses[use, h - 1])[0, 1])
                     if np.std(pred_pt[use, h - 1]) > 0 else np.nan}
                if pred_q is not None:
                    r["coverage_80"] = coverage(yt, pred_q[use, h - 1])
                    r["pinball"] = mean_pinball(yt, pred_q[use, h - 1])
                rows.append(r)
    out = pd.DataFrame(rows)
    out["skill_vs_naive"] = 1 - out["mae_log"] / out["mae_naive"]
    return out


def _iter_models(point, quant):
    """Yield ((name, seed, family), predictions) for everything scored.

    Point predictions are [N_all, H]; quantile ones are already restricted to the
    test rows, [N_test, H, Q].
    """
    for name, pred in point.items():
        family = ("reference" if "Track B" in name else "baseline")
        if isinstance(pred, dict):                        # one array per seed
            for sd, arr in pred.items():
                yield (name, sd, "reference"), arr
        else:
            yield (name, None, family), pred
    for (name, seed), pred in quant.items():
        family = "baseline" if "empirical" in name else (
            "ensemble" if seed == "ensemble" else "network")
        yield (name, seed, family), pred


def summarise(per_seed):
    """Mean and spread over seeds, per (model, horizon, subset)."""
    g = per_seed.groupby(["model", "family", "horizon", "subset"], as_index=False, dropna=False)
    out = g.agg(mae_log=("mae_log", "mean"), mae_log_sd=("mae_log", "std"),
                skill_vs_naive=("skill_vs_naive", "mean"),
                gain_ci_low=("gain_ci_low", "mean"), gain_ci_high=("gain_ci_high", "mean"),
                gain_vs_ses=("gain_vs_ses", "mean"),
                ses_ci_low=("ses_ci_low", "mean"), ses_ci_high=("ses_ci_high", "mean"),
                corr_with_ses=("corr_with_ses", "mean"),
                coverage_80=("coverage_80", "mean"), pinball=("pinball", "mean"),
                n=("n", "first"), test_months=("test_months", "first"),
                n_seeds=("seed", lambda s: int(s.notna().sum()) or 1))
    return out.sort_values(["subset", "horizon", "mae_log"])


# =====================================================================
# Rolling-origin backtest
# =====================================================================
def rolling_origin(p, origins=SEQ_ROLLING_ORIGINS, block=SEQ_ROLLING_BLOCK,
                   archs=SEQ_ROLLING_ARCHS, window=SEQ_ROLLING_WINDOW,
                   n_seeds=N_SEEDS, n_jobs=SEQ_N_JOBS, **train_kw):
    """Refit at every origin and forecast the next `block` months of origins.

    The main split freezes each model at 2025-03 and scores 16 months with it.
    That is one test window, and the hybrid was added after seeing it. This
    re-runs the deciding comparison -- the two N-BEATS variants against naive,
    drift and SES -- at eight origins, each with its own inner validation, early
    stopping, SES alpha, drift and scaler, all from data up to that origin.

    Returns one row per (test sample, horizon) with every model's median forecast.
    """
    out = []
    for origin in origins:
        _, refits, samples, splits = train_sequence_models(
            p, archs=archs, n_seeds=n_seeds, windows=[window], n_jobs=n_jobs,
            train_end=origin, test_months=block, **train_kw)
        smp = samples[window]
        point, info = baseline_forecasts(p, smp, splits)
        te_rows, te_mask = splits["test"]
        meta = smp["meta"][te_rows].reset_index(drop=True)
        mid = len(SEQ_QUANTILES) // 2
        preds = {"Naive (last month)": point["Naive (last month)"][te_rows],
                 "Drift (last + mean growth)": point["Drift (last + mean growth)"][te_rows],
                 "SES": point["SES"][te_rows]}
        for arch in archs:
            mine = [r["test"][..., mid] for r in refits if r["model"] == arch]
            preds[f"{arch} x{len(mine)} ensemble"] = np.median(mine, axis=0)
            for r in refits:
                if r["model"] == arch:
                    preds[f"{arch} | seed {r['seed']}"] = r["test"][..., mid]
        for h in range(1, SEQ_HORIZON + 1):
            use = te_mask[te_rows][:, h - 1]
            frame = meta.loc[use, ["state", "month"]].copy()
            frame["origin"] = pd.Timestamp(origin)
            frame["horizon"] = h
            frame["y"] = smp["y"][te_rows][use, h - 1]
            for name, pr in preds.items():
                frame[name] = pr[use, h - 1]
            frame["ses_alpha"] = info["ses_alpha"]
            out.append(frame)
    return pd.concat(out, ignore_index=True)


def score_rolling(rows, majors, main_test_start=VOLUME_TRAIN_END):
    """Pooled scores over the rolling blocks, overall and split at the main test window.

    "before" is every forecast made before the main split's test window: months
    whose network results had not been looked at when the hybrid was added.
    """
    models = [c for c in rows.columns
              if c not in {"state", "month", "origin", "horizon", "y", "ses_alpha"}
              and "| seed" not in c]
    seeds = [c for c in rows.columns if "| seed" in c]
    cut = pd.Timestamp(main_test_start)
    periods = {"all": rows["month"].notna(), "before": rows["month"] <= cut,
               "main window": rows["month"] > cut}
    out = []
    for h in sorted(rows["horizon"].unique()):
        for subset in ("all", "major"):
            for period, pmask in periods.items():
                r = rows[(rows["horizon"] == h) & pmask]
                if subset == "major":
                    r = r[r["state"].isin(majors)]
                if r.empty:
                    continue
                e_naive = np.abs(r["y"] - r["Naive (last month)"]).to_numpy()
                e_ses = np.abs(r["y"] - r["SES"]).to_numpy()
                months = r["month"].to_numpy()
                for name in models:
                    e = np.abs(r["y"] - r[name]).to_numpy()
                    vs_n = month_bootstrap(e_naive, e, months)
                    vs_s = month_bootstrap(e_ses, e, months)
                    sd = np.nan
                    arch = name.split(" x")[0]
                    own = [c for c in seeds if c.startswith(arch + " |")]
                    if len(own) > 1 and "ensemble" in name:
                        sd = float(np.std([np.abs(r["y"] - r[c]).mean() for c in own], ddof=1))
                    out.append({"model": name, "horizon": h, "subset": subset,
                                "period": period, "n": len(r),
                                "test_months": int(r["month"].nunique()),
                                "mae_log": float(e.mean()), "seed_sd": sd,
                                "skill_vs_naive": 1 - e.mean() / e_naive.mean(),
                                "gain_ci_low": vs_n["gain_ci_low"],
                                "gain_ci_high": vs_n["gain_ci_high"],
                                "skill_vs_ses": 1 - e.mean() / e_ses.mean(),
                                "ses_ci_low": vs_s["gain_ci_low"],
                                "ses_ci_high": vs_s["gain_ci_high"]})
    return pd.DataFrame(out)


def rolling_by_block(rows, horizon=1):
    """MAE per origin block at one horizon, to show whether one block carries the result."""
    models = [c for c in rows.columns
              if c not in {"state", "month", "origin", "horizon", "y", "ses_alpha"}
              and "| seed" not in c]
    r = rows[rows["horizon"] == horizon]
    g = r.groupby("origin")
    out = pd.DataFrame({m: g.apply(lambda d, m=m: np.abs(d["y"] - d[m]).mean()) for m in models})
    out.insert(0, "test_months", g["month"].nunique())
    out.insert(1, "ses_alpha", g["ses_alpha"].first())
    return out.reset_index()


# =====================================================================
# Run
# =====================================================================
def run(n_jobs=SEQ_N_JOBS):
    RESULTS.mkdir(parents=True, exist_ok=True)
    p = seq_panel()
    selection, refits, samples_by_w, splits = train_sequence_models(p, n_jobs=n_jobs)
    samples = samples_by_w[SEQ_WINDOWS[0]]
    te_rows, _ = splits["test"]
    tr_rows, tr_mask = splits["train"]

    lvl = p[p["month"] <= VOLUME_TRAIN_END].groupby("state")["ev_total"].mean()
    majors = sorted(lvl[lvl >= SEQ_MAJOR_STATE_MIN_MONTHLY].index)

    point, base_info = baseline_forecasts(p, samples, splits)
    ref, mlp = reference_forecasts(p, samples, splits)
    point.update(ref)
    point["MLP (16) (Track B features)"] = mlp

    quant = {}
    for r in refits:
        quant[(r["model"], r["seed"])] = r["test"]
    for arch in ALL_ARCHS:
        preds = [r["test"] for r in refits if r["model"] == arch]
        quant[(f"{arch} x{len(preds)} ensemble", "ensemble")] = np.median(preds, axis=0)
    for name, short in (("Naive (last month)", "Naive"), ("SES", "SES"),
                        ("Drift (last + mean growth)", "Drift")):
        quant[(f"{short} + empirical quantiles", None)] = \
            empirical_quantiles(samples, splits, point[name])[te_rows]

    per_seed = score_all(samples, splits, point, quant, majors)
    summary = summarise(per_seed)

    # training error, to separate overfitting from absent signal (as Track B does)
    diag = []
    y_tr, m_tr = samples["y"][tr_rows], tr_mask[tr_rows]
    y_te, m_te = samples["y"][te_rows], splits["test"][1][te_rows]
    for arch in ALL_ARCHS:
        mine = [r for r in refits if r["model"] == arch]
        tr = np.mean([np.mean(np.abs(y_tr[m_tr[:, 0], 0] - r["train"][m_tr[:, 0], 0, 1])) for r in mine])
        te = np.mean([np.mean(np.abs(y_te[m_te[:, 0], 0] - r["test"][m_te[:, 0], 0, 1])) for r in mine])
        diag.append({"model": arch, "mae_log_train": tr, "mae_log_test": te})
    diag.append({"model": "Naive (last month)",
                 "mae_log_train": float(np.mean(np.abs(y_tr[m_tr[:, 0], 0]))),
                 "mae_log_test": float(np.mean(np.abs(y_te[m_te[:, 0], 0])))})
    diag = pd.DataFrame(diag)
    diag["gap"] = diag["mae_log_test"] - diag["mae_log_train"]

    # per state, for the architecture with the lowest validation loss -- chosen
    # without looking at the test months
    best_arch = (selection[selection["chosen"]].groupby("model")["val_loss"].mean().idxmin())
    ens = quant[(f"{best_arch} x{N_SEEDS} ensemble", "ensemble")][:, 0, 1]
    meta_te = samples["meta"][te_rows].reset_index(drop=True)
    by_state = []
    for state, idx in meta_te.groupby("state").groups.items():
        idx = np.asarray(idx)
        use = idx[m_te[idx, 0]]
        e_m = np.abs(y_te[use, 0] - ens[use]).mean()
        e_n = np.abs(y_te[use, 0]).mean()
        by_state.append({"state": state, "model": f"{best_arch} ensemble",
                         "mean_level": float(lvl.get(state, np.nan)),
                         "major": state in majors, "n_test": len(use),
                         "mae_log_model": e_m, "mae_log_naive": e_n,
                         "skill_vs_naive": 1 - e_m / e_n if e_n else np.nan})
    by_state = pd.DataFrame(by_state).sort_values("mean_level", ascending=False)

    info = {"states": len(samples["states"]), "major_states": len(majors),
            "train_samples": int(tr_rows.sum()), "test_samples": int(te_rows.sum()),
            "train_end": VOLUME_TRAIN_END,
            "test_origins": f"{samples['meta'].loc[te_rows, 'month'].min().date()}"
                            f" to {samples['meta'].loc[te_rows, 'month'].max().date()}",
            "channels": len(CHANNELS), "windows_tried": SEQ_WINDOWS,
            "best_by_validation": best_arch, **base_info}

    selection.to_csv(RESULTS / "seq_selection.csv", index=False)
    per_seed.to_csv(RESULTS / "seq_per_seed.csv", index=False)
    summary.to_csv(RESULTS / "seq_summary.csv", index=False)
    diag.to_csv(RESULTS / "seq_fit_diagnostics.csv", index=False)
    by_state.to_csv(RESULTS / "seq_by_state.csv", index=False)
    pd.Series(info).to_csv(RESULTS / "seq_info.csv", header=["value"])

    rolling = rolling_origin(p, n_jobs=n_jobs)
    roll_summary = score_rolling(rolling, majors)
    roll_blocks = rolling_by_block(rolling)
    roll_summary.to_csv(RESULTS / "seq_rolling_summary.csv", index=False)
    roll_blocks.to_csv(RESULTS / "seq_rolling_by_block.csv", index=False)

    return {"selection": selection, "summary": summary, "diagnostics": diag,
            "by_state": by_state, "info": info, "rolling": roll_summary,
            "rolling_blocks": roll_blocks}


if __name__ == "__main__":
    out = run()
    pd.set_option("display.width", 220, "display.max_columns", 30, "display.max_rows", 200)
    print("\n=== design ===")
    for k, v in out["info"].items():
        print(f"  {k}: {v}")
    sel = out["selection"]
    print("\n=== validation: mean loss by window (chosen marked) ===")
    print(sel.groupby(["model", "window", "chosen"], as_index=False)
          .agg(val_loss=("val_loss", "mean"), best_epoch=("best_epoch", "mean"),
               seconds=("seconds", "mean"), params=("params", "first")).to_string(index=False))
    s = out["summary"]
    cols = ["model", "family", "mae_log", "mae_log_sd", "skill_vs_naive",
            "gain_ci_low", "gain_ci_high", "ses_ci_low", "ses_ci_high", "corr_with_ses",
            "coverage_80", "pinball", "n_seeds"]
    for subset in ("all", "major"):
        for h in SEQ_REPORT_HORIZONS:
            sub = s[(s["subset"] == subset) & (s["horizon"] == h)]
            print(f"\n=== h={h}, {subset} states (n={sub['n'].iloc[0]}, "
                  f"{sub['test_months'].iloc[0]} test months) ===")
            print(sub[cols].to_string(index=False))
    print("\n=== train vs test, h=1 ===")
    print(out["diagnostics"].to_string(index=False))
    rs = out["rolling"]
    rcols = ["model", "mae_log", "seed_sd", "skill_vs_naive", "gain_ci_low", "gain_ci_high",
             "skill_vs_ses", "ses_ci_low", "ses_ci_high"]
    for h in SEQ_REPORT_HORIZONS:
        for period in ("all", "before", "main window"):
            sub = rs[(rs["horizon"] == h) & (rs["subset"] == "all") & (rs["period"] == period)]
            print(f"\n=== rolling origin, h={h}, {period} (n={sub['n'].iloc[0]}, "
                  f"{sub['test_months'].iloc[0]} months) ===")
            print(sub.sort_values("mae_log")[rcols].to_string(index=False))
    print("\n=== rolling origin, MAE by block, h=1 ===")
    print(out["rolling_blocks"].to_string(index=False))
    bs = out["by_state"]
    print(f"\n=== per state, h=1: {bs['model'].iloc[0]} beats naive in "
          f"{int((bs['skill_vs_naive'] > 0).sum())}/{len(bs)} states "
          f"({int((bs[bs['major']]['skill_vs_naive'] > 0).sum())}/{int(bs['major'].sum())} major) ===")
