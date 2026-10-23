"""Track C's networks: sequence models that read the raw monthly window.

Track B gave a feedforward MLP 21 engineered lag columns and found nothing a
random walk does not already have. That rules out an MLP on those lags. It does
not rule out the lags being the wrong summary, which is the hypothesis these
models test: they read the window itself, one vector per month, and learn their
own summary of it.

One architecture per family, each kept small, because ~2,400 training windows
cannot carry more:

  GRU          recurrent, the default sequence model
  LSTM         recurrent with a gated memory cell
  TCN          dilated causal convolutions (Bai, Kolter & Koltun 2018)
  Transformer  self-attention over the window
  N-BEATS      a deep residual MLP on the univariate window (Oreshkin et al.
               2020), the network that beat the statistical methods on M4

Every model maps (sequence [B, L, C], static [B, S], state index [B]) to
[B, H, Q]: H horizons by Q quantiles of the log change from the origin month.

Two design choices shared by all of them:

* **The forecast is a change, not a level.** Track B showed that predicting the
  level makes a network re-learn the identity map before it can model anything.
* **The head starts at "no change".** Its weights are zero-initialised, so an
  untrained network forecasts exactly the random walk and training has to earn
  every departure from it. That is a prior, not a constraint.
"""
import copy
import time

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn


# =====================================================================
# Shared pieces
# =====================================================================
def order_quantiles(raw, mid):
    """Rebuild raw outputs [..., Q] so the quantiles cannot cross.

    The median is taken as is; each quantile below it is the next one up minus a
    softplus, each above it the next one down plus a softplus. Crossing quantiles
    would make the 80% interval meaningless, and sorting them after the fact
    hides the problem from the loss.
    """
    med = raw[..., mid:mid + 1]
    below = F.softplus(raw[..., :mid]).flip(-1).cumsum(-1).flip(-1)
    above = F.softplus(raw[..., mid + 1:]).cumsum(-1)
    return torch.cat([med - below, med, med + above], dim=-1)


def spread_bias(horizon, quantiles, init_spread=0.2):
    """Initial raw outputs: median 0, every gap softplus^-1(init_spread) wide."""
    mid = len(quantiles) // 2
    if not np.isclose(quantiles[mid], 0.5):
        raise ValueError("the middle quantile must be the median")
    bias = torch.zeros(horizon, len(quantiles))
    bias[:, np.arange(len(quantiles)) != mid] = float(np.log(np.expm1(init_spread)))
    return bias, mid


class QuantileHead(nn.Module):
    """Linear map to H x Q ordered quantiles, starting at "no change"."""

    def __init__(self, d_in, horizon, quantiles):
        super().__init__()
        bias, self.mid = spread_bias(horizon, quantiles)
        self.h, self.q = horizon, len(quantiles)
        self.lin = nn.Linear(d_in, horizon * self.q)
        nn.init.zeros_(self.lin.weight)
        with torch.no_grad():
            self.lin.bias.copy_(bias.flatten())

    def forward(self, z):
        return order_quantiles(self.lin(z).view(-1, self.h, self.q), self.mid)


def _context(n_static, n_states, emb):
    """What every model but N-BEATS appends to its sequence summary."""
    return nn.Embedding(n_states, emb), n_static + emb


# =====================================================================
# Architectures
# =====================================================================
class RNNForecaster(nn.Module):
    """GRU or LSTM over the window; the last hidden state is the summary.

    Windows are left-padded with zeros where a state's history is shorter, and a
    `present` channel tells the cell which steps are padding.
    """

    def __init__(self, n_channels, n_static, n_states, horizon, quantiles,
                 cell="gru", hidden=32, emb=4, dropout=0.1, **_):
        super().__init__()
        rnn = nn.GRU if cell == "gru" else nn.LSTM
        self.rnn = rnn(n_channels, hidden, batch_first=True)
        self.emb, extra = _context(n_static, n_states, emb)
        self.mix = nn.Sequential(nn.Linear(hidden + extra, hidden), nn.ReLU(),
                                 nn.Dropout(dropout))
        self.head = QuantileHead(hidden, horizon, quantiles)

    def forward(self, x, s, idx):
        out, _ = self.rnn(x)
        return self.head(self.mix(torch.cat([out[:, -1], self.emb(idx), s], -1)))


class _CausalBlock(nn.Module):
    """Two dilated convolutions padded on the left only, plus a residual path."""

    def __init__(self, c_in, c_out, kernel, dilation, dropout):
        super().__init__()
        self.pad = (kernel - 1) * dilation
        self.conv1 = nn.Conv1d(c_in, c_out, kernel, dilation=dilation)
        self.conv2 = nn.Conv1d(c_out, c_out, kernel, dilation=dilation)
        self.drop = nn.Dropout(dropout)
        self.skip = nn.Conv1d(c_in, c_out, 1) if c_in != c_out else nn.Identity()

    def forward(self, x):
        y = self.drop(F.relu(self.conv1(F.pad(x, (self.pad, 0)))))
        y = self.drop(F.relu(self.conv2(F.pad(y, (self.pad, 0)))))
        return F.relu(y + self.skip(x))


class TCNForecaster(nn.Module):
    """Temporal convolutional network; the output at the origin month is the summary.

    Dilations 1, 2, 4, 8 with kernel 3 give a receptive field of 61 months, more
    than either window, so the last output sees the whole window.
    """

    def __init__(self, n_channels, n_static, n_states, horizon, quantiles,
                 channels=32, kernel=3, dilations=(1, 2, 4, 8), emb=4, dropout=0.1, **_):
        super().__init__()
        blocks, c_in = [], n_channels
        for d in dilations:
            blocks.append(_CausalBlock(c_in, channels, kernel, d, dropout))
            c_in = channels
        self.tcn = nn.Sequential(*blocks)
        self.emb, extra = _context(n_static, n_states, emb)
        self.mix = nn.Sequential(nn.Linear(channels + extra, channels), nn.ReLU(),
                                 nn.Dropout(dropout))
        self.head = QuantileHead(channels, horizon, quantiles)

    def forward(self, x, s, idx):
        z = self.tcn(x.transpose(1, 2))[:, :, -1]
        return self.head(self.mix(torch.cat([z, self.emb(idx), s], -1)))


class TransformerForecaster(nn.Module):
    """Two encoder layers of self-attention; the origin month's token is the summary.

    Positions are learned and counted back from the origin, so "the month before
    the origin" has the same embedding whatever the window length. Padding steps
    are masked out of the attention entirely.
    """

    def __init__(self, n_channels, n_static, n_states, horizon, quantiles, window,
                 d_model=32, heads=4, layers=2, ff=64, emb=4, dropout=0.1, **_):
        super().__init__()
        self.proj = nn.Linear(n_channels, d_model)
        self.pos = nn.Parameter(torch.randn(1, window, d_model) * 0.02)
        layer = nn.TransformerEncoderLayer(d_model, heads, ff, dropout, batch_first=True)
        self.enc = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.emb, extra = _context(n_static, n_states, emb)
        self.mix = nn.Sequential(nn.Linear(d_model + extra, d_model), nn.ReLU(),
                                 nn.Dropout(dropout))
        self.head = QuantileHead(d_model, horizon, quantiles)

    def forward(self, x, s, idx):
        L = x.shape[1]
        pad = x[..., -1] == 0                  # the last channel is `present`
        h = self.enc(self.proj(x) + self.pos[:, -L:], src_key_padding_mask=pad)
        return self.head(self.mix(torch.cat([h[:, -1], self.emb(idx), s], -1)))


class _NBeatsBlock(nn.Module):
    def __init__(self, window, width, layers, horizon, n_q):
        super().__init__()
        net, d = [], 2 * window                # the residual window plus its mask
        for _ in range(layers):
            net += [nn.Linear(d, width), nn.ReLU()]
            d = width
        self.fc = nn.Sequential(*net)
        self.backcast = nn.Linear(width, window)
        self.forecast = nn.Linear(width, horizon * n_q)
        nn.init.zeros_(self.forecast.weight)
        nn.init.zeros_(self.forecast.bias)

    def forward(self, r, mask):
        z = self.fc(torch.cat([r, mask], -1))
        return self.backcast(z), self.forecast(z)


class NBeatsForecaster(nn.Module):
    """N-BEATS, generic configuration, scaled down to the data.

    Univariate by design: it reads only the window of log levels relative to the
    origin month. Each block explains part of the window (backcast), passes on
    what it could not, and contributes a partial forecast; the forecasts sum.
    The original stacks 30 blocks of 4 x 512 units for 100k series; 3 blocks of
    3 x 64 is what 2,400 windows can support.

    The block forecasts sum into raw quantile outputs, which go through the same
    non-crossing transform as every other model's head.
    """

    def __init__(self, n_channels, n_static, n_states, horizon, quantiles, window,
                 blocks=3, width=64, layers=3, level_channel=0, **_):
        super().__init__()
        self.level_channel = level_channel
        self.blocks = nn.ModuleList(
            _NBeatsBlock(window, width, layers, horizon, len(quantiles)) for _ in range(blocks))
        bias, self.mid = spread_bias(horizon, quantiles)
        self.bias = nn.Parameter(bias)
        self.h, self.q = horizon, len(quantiles)

    def forward(self, x, s, idx):
        r, mask = x[..., self.level_channel], x[..., -1]
        total = 0.0
        for block in self.blocks:
            back, fore = block(r, mask)
            r = (r - back) * mask
            total = total + fore
        return order_quantiles(total.view(-1, self.h, self.q) + self.bias, self.mid)


class FeatureMLP(nn.Module):
    """A control, not a sequence model: Track B's MLP (16), trained the Track C way.

    It reads Track B's 21 engineered features (passed as the static vector) and
    ignores the window. Everything else -- pinball loss, early stopping, the
    zero-initialised head, six horizons -- is what the sequence models get. If it
    does as well as they do, Track B lost to the random walk because of how its
    networks were trained, not because the lags were the wrong summary.
    """

    def __init__(self, n_channels, n_static, n_states, horizon, quantiles,
                 hidden=16, dropout=0.1, **_):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(n_static, hidden), nn.ReLU(), nn.Dropout(dropout))
        self.head = QuantileHead(hidden, horizon, quantiles)

    def forward(self, x, s, idx):
        return self.head(self.net(s))


ARCHITECTURES = {
    "GRU":         lambda **k: RNNForecaster(cell="gru", **k),
    "LSTM":        lambda **k: RNNForecaster(cell="lstm", **k),
    "TCN":         lambda **k: TCNForecaster(**k),
    "Transformer": lambda **k: TransformerForecaster(**k),
    "N-BEATS":     lambda **k: NBeatsForecaster(**k),
    "MLP (16), Track C training": lambda **k: FeatureMLP(**k),
}


def build(name, seed, **dims):
    """Construct an architecture with its weights drawn from `seed`."""
    torch.manual_seed(seed)
    return ARCHITECTURES[name](**dims)


def n_params(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


# =====================================================================
# Loss, training, prediction
# =====================================================================
def pinball_loss(pred, y, mask, quantiles):
    """Mean quantile loss over the horizons that have a target.

    pred [B, H, Q], y [B, H], mask [B, H]. At q = 0.5 this is half the absolute
    error, so the median head is trained on the metric it is scored on.
    """
    q = torch.as_tensor(quantiles, dtype=pred.dtype, device=pred.device)
    diff = y.unsqueeze(-1) - pred
    loss = torch.maximum(q * diff, (q - 1) * diff).mean(-1)
    return (loss * mask).sum() / mask.sum().clamp(min=1.0)


def _tensors(data):
    return {k: torch.as_tensor(v) for k, v in data.items()}


def fit(model, train, quantiles, val=None, epochs=300, patience=30, batch=64,
        lr=1e-3, weight_decay=1e-4, seed=0):
    """Train with AdamW; early-stop on `val` if given, else run exactly `epochs`.

    `train` and `val` are dicts of arrays: x [N, L, C], s [N, S], idx [N],
    y [N, H], m [N, H] (1 where the target exists and may be used).

    Returns (model at its best epoch, best epoch, best validation loss, seconds).
    The best epoch is what a refit on the full training window then runs for.
    """
    start = time.perf_counter()
    tr = _tensors(train)
    va = _tensors(val) if val is not None else None
    n = len(tr["y"])
    gen = torch.Generator().manual_seed(seed)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    best_loss, best_epoch, best_state, stale = np.inf, epochs, None, 0
    for epoch in range(1, epochs + 1):
        model.train()
        order = torch.randperm(n, generator=gen)
        for i in range(0, n, batch):
            b = order[i:i + batch]
            loss = pinball_loss(model(tr["x"][b], tr["s"][b], tr["idx"][b]),
                                tr["y"][b], tr["m"][b], quantiles)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()

        if va is None:
            continue
        model.eval()
        with torch.no_grad():
            v = float(pinball_loss(model(va["x"], va["s"], va["idx"]), va["y"], va["m"], quantiles))
        if v < best_loss - 1e-6:
            best_loss, best_epoch, best_state, stale = v, epoch, copy.deepcopy(model.state_dict()), 0
        else:
            stale += 1
            if stale >= patience:
                break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, best_epoch, (best_loss if va is not None else np.nan), time.perf_counter() - start


def predict(model, data):
    """[N, H, Q] quantile forecasts of the log change from the origin."""
    t = _tensors(data)
    model.eval()
    with torch.no_grad():
        return model(t["x"], t["s"], t["idx"]).numpy()
