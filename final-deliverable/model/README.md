# Model artifacts

Two kinds of model are served, and they live here differently.

**The outlook** -- next-month announcement probabilities, national and by
state -- is fitted. Its artifact is [`outlook.json`](outlook.json), written by
[`build_outlook.py`](build_outlook.py), described in
[`outlook-card.md`](outlook-card.md) and baked into the image at
`/app/model/outlook.json`. `test_outlook_build.py` fails when the committed
artifact no longer matches `data/clean/`; re-run the build script to fix it.

**The per-company signal** has no fitted model. None of the models selected in
development produce per-company output, so the container serves the null
baseline described in [`../app/model.py`](../app/model.py). The rest of this
file is the contract a fitted company model would have to meet.

## The contract

A model is anything satisfying the `SignalModel` protocol in `app/model.py`:

| member | meaning |
|---|---|
| `name` | stable identifier, reported on `/metadata` |
| `version` | bump on every refit; consumers key cache invalidation off it |
| `description` | one paragraph a consumer can read without the code |
| `score_units` | how to read `score`; the baseline's is `ratio_capex_to_depreciation` |
| `required_features` | panel columns the model depends on |
| `signals(store)` | returns one `RawSignal` per company it can score |

`signals()` must **skip** a company it cannot score rather than emit a filler
value. A consumer can tell "absent" from "zero"; it cannot tell a real zero from
a filler one.

## Wiring one in

1. Add the model's runtime dependencies to
   [`../requirements.txt`](../requirements.txt).
2. Implement `app/model.py::_load_artifact` to deserialise the artifact and
   return a `SignalModel`.
3. Put the artifact here and set `MODEL_ARTIFACT=/app/model/<file>`. Add a
   `COPY final-deliverable/model/<file> /app/model/<file>` to the Dockerfile to
   bake it in, or mount it.
4. Replace `test_present_but_unimplemented_artifact_fails_loudly` in
   `../tests/test_model.py` with a test that loads a real fixture artifact. The
   protocol check (`test_baseline_satisfies_the_protocol`) should be extended to
   cover the fitted model too.

A `MODEL_ARTIFACT` that is set but unloadable is a **fatal** error, not a
fallback to the baseline. That is deliberate: the two serve identical-looking
responses, and a silent downgrade would be discovered in the results rather than
at deploy time. `/ready` returns 503 and names the reason.

## What the container already has on disk

`FEATURE_STORE` (`/app/feature-store` in the image) holds more than the annual
panel the baseline reads. All of these are baked in, so a fitted model can use
them without a new base layer:

```
panel_company_annual.csv            the panel app/features.py reads today
panel_company_halfyearly.csv        asset growth, 6 half-year deltas
company_capex_annual.csv            capex and cash-flow lines, pre-join
company_assets_halfyearly.csv       productive-asset stocks
ev_production_model_monthly.csv     SIAM production, month x OEM x model
ev_registrations_maker_monthly.csv  VAHAN registrations, month x maker
ev_registrations_segment_monthly.csv
ev_registrations_state_monthly.csv
target_companies.csv                the 52-company target set and tiers
```

Read them, do not re-derive them. `scripts/` in the repo root is the single
source of truth for feature construction; a second implementation inside the
service would drift from it.

## Keep a model card beside the artifact

Commit a short `<name>-card.md` next to any artifact recording: the training
window, the panel file and its mtime, the specification, what it was compared
against, and the headline out-of-sample number. The deliverable is a research
result, so the provenance of the numbers it emits is part of it.

Artifacts themselves are usually too large for git -- if that happens here, keep
the card committed and the binary out, and record where the binary lives.
