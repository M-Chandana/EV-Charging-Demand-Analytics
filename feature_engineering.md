# Issue #12: Feature Engineering

## Inputs and outputs

The feature-engineering notebook and implementation use the validated
`acn_clean_sessions.csv` file from Issue #9.

| Output | Grain | Purpose |
|---|---|---|
| `feature_engineered_sessions.csv` | One row per charging session | Session-level analytics, segmentation, and station/driver behaviour |
| `feature_engineered_daily.csv` | One row per observed local calendar day | Modelling-ready daily demand features |
| `feature_validation_summary.csv` | One row per validation check | Reproducible quality evidence |

Run the implementation from the repository root with:

```text
python feature_engineering.py
```

## Feature groups

- **Time:** local arrival hour/minute, weekday/weekend, month, ISO week,
  quarter, season, time block, business-hours, morning, and overnight flags.
- **Duration:** idle hours, charging ratio, long-stay and overnight-stay flags,
  available charging time, and departure slack.
- **Energy and demand:** energy per connected/charging hour, requested-energy
  gap and fill ratio, energy bands, 13–14 kWh default-spike flag, and
  high-energy flag.
- **Station usage:** station session count, station energy statistics, station
  share, rank, total energy, and top-quartile indicator.
- **Behaviour:** user/input availability, requested energy, payment-required
  input, and departure-related fields retained from preprocessing.
- **Daily forecasting:** observed session count, energy, duration, station
  coverage, behaviour shares, calendar fields, and lag/rolling demand features.

Daily lag and rolling features are shifted before calculation. Therefore each
row only uses demand from earlier dates and does not leak the current day's
target into its predictors. The first dates may have missing lag/rolling
values and should be excluded or imputed inside a time-ordered modelling
pipeline.

## Validation

The implementation checks that session IDs remain unique, the row count is
preserved, durations and ratios remain physically valid, daily dates are
unique, daily counts are positive, and lag features are available only after
the required history. All checks are recorded in
`feature_validation_summary.csv`.
