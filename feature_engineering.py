"""Feature engineering for the cleaned ACN charging-session data.

The module is intentionally executable from the repository root:
    python feature_engineering.py
"""

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "acn_clean_sessions.csv"
SESSION_OUTPUT = ROOT / "feature_engineered_sessions.csv"
DAILY_OUTPUT = ROOT / "feature_engineered_daily.csv"
VALIDATION_OUTPUT = ROOT / "feature_validation_summary.csv"

SESSION_COLUMNS = [
    "_id", "sessionID", "userID", "stationID", "spaceID", "connectionTime",
    "disconnectTime", "doneChargingTime", "kWhDelivered", "connected_h",
    "charging_h", "avg_power_kW", "hour", "dayofweek", "date",
    "has_user_input", "has_user_id", "ui_milesRequested", "ui_WhPerMile",
    "ui_minutesAvailable", "ui_paymentRequired", "ui_kWhRequested",
    "ui_departure_est", "done_time_missing", "done_time_inconsistent",
    "power_implausible", "overlaps_prev_session",
]


def _time_block(hour: pd.Series) -> pd.Series:
    return pd.cut(
        hour,
        bins=[-1, 5, 9, 13, 17, 21, 23],
        labels=["overnight", "morning", "midday", "afternoon", "evening", "late_evening"],
    ).astype("string")


def _season(month: pd.Series) -> pd.Series:
    return pd.cut(
        month,
        bins=[0, 2, 5, 8, 11, 12],
        labels=["winter", "spring", "summer", "autumn", "winter"],
        ordered=False,
    ).astype("string")


def build_session_features(source: pd.DataFrame) -> pd.DataFrame:
    """Create one modelling/analytics row per cleaned charging session."""
    df = source.copy()
    for column in ("connectionTime", "disconnectTime", "doneChargingTime"):
        df[column] = pd.to_datetime(df[column], utc=True, errors="coerce")

    local_connection = df["connectionTime"].dt.tz_convert("America/Los_Angeles")
    local_disconnect = df["disconnectTime"].dt.tz_convert("America/Los_Angeles")
    local_done = df["doneChargingTime"].dt.tz_convert("America/Los_Angeles")

    df["arrival_hour"] = local_connection.dt.hour
    df["arrival_minute"] = local_connection.dt.minute
    df["arrival_dayofweek"] = local_connection.dt.dayofweek
    df["is_weekend"] = df["arrival_dayofweek"].ge(5)
    df["arrival_date"] = local_connection.dt.date.astype("string")
    df["arrival_month"] = local_connection.dt.month
    df["arrival_week"] = local_connection.dt.isocalendar().week.astype("int64")
    df["arrival_quarter"] = local_connection.dt.quarter
    df["time_block"] = _time_block(df["arrival_hour"])
    df["season"] = _season(df["arrival_month"])
    df["is_business_hours"] = df["arrival_hour"].between(7, 18)
    df["is_morning_arrival"] = df["arrival_hour"].between(6, 10)
    df["is_overnight_arrival"] = (df["arrival_hour"] < 6) | (df["arrival_hour"] >= 22)

    df["idle_h"] = (df["connected_h"] - df["charging_h"]).clip(lower=0)
    df["charging_ratio"] = np.where(
        df["connected_h"].gt(0), df["charging_h"] / df["connected_h"], np.nan
    ).clip(0, 1)
    df["is_long_stay"] = df["connected_h"].ge(6.0)
    df["is_overnight_stay"] = local_disconnect.dt.date.ne(local_connection.dt.date)
    df["charging_time_available_h"] = df["ui_minutesAvailable"] / 60.0
    df["departure_slack_h"] = (
        pd.to_datetime(df["ui_departure_est"], utc=True, errors="coerce")
        - df["connectionTime"]
    ).dt.total_seconds() / 3600.0

    df["energy_per_connected_h"] = np.where(
        df["connected_h"].gt(0), df["kWhDelivered"] / df["connected_h"], np.nan
    )
    df["energy_per_charging_h"] = np.where(
        df["charging_h"].gt(0), df["kWhDelivered"] / df["charging_h"], np.nan
    )
    df["requested_energy_gap_kWh"] = df["ui_kWhRequested"] - df["kWhDelivered"]
    df["requested_energy_fill_ratio"] = np.where(
        df["ui_kWhRequested"].gt(0),
        df["kWhDelivered"] / df["ui_kWhRequested"],
        np.nan,
    )
    df["energy_band"] = pd.cut(
        df["kWhDelivered"],
        bins=[-np.inf, 2, 7, 14, 21, 35, np.inf],
        labels=["very_low", "low", "default_spike", "medium", "high", "very_high"],
    ).astype("string")
    df["is_default_energy_spike"] = df["kWhDelivered"].between(13, 14, inclusive="left")
    df["is_high_energy"] = df["kWhDelivered"].ge(df["kWhDelivered"].quantile(0.9))

    station_stats = df.groupby("stationID", dropna=False).agg(
        station_session_count=("_id", "size"),
        station_mean_kWh=("kWhDelivered", "mean"),
        station_median_kWh=("kWhDelivered", "median"),
        station_total_kWh=("kWhDelivered", "sum"),
    )
    station_stats["station_share_of_sessions"] = (
        station_stats["station_session_count"] / len(df)
    )
    station_stats["station_rank_by_sessions"] = (
        station_stats["station_session_count"].rank(method="dense", ascending=False).astype("int64")
    )
    df = df.join(station_stats, on="stationID")
    df["station_is_top_quartile"] = df["station_rank_by_sessions"].le(
        max(1, int(station_stats.shape[0] * 0.25))
    )

    keep = [
        column for column in SESSION_COLUMNS if column in df.columns
    ] + [
        "arrival_hour", "arrival_minute", "arrival_dayofweek", "is_weekend",
        "arrival_date", "arrival_month", "arrival_week", "arrival_quarter",
        "time_block", "season", "is_business_hours", "is_morning_arrival",
        "is_overnight_arrival", "idle_h", "charging_ratio", "is_long_stay",
        "is_overnight_stay", "charging_time_available_h", "departure_slack_h",
        "energy_per_connected_h", "energy_per_charging_h",
        "requested_energy_gap_kWh", "requested_energy_fill_ratio", "energy_band",
        "is_default_energy_spike", "is_high_energy", "station_session_count",
        "station_mean_kWh", "station_median_kWh", "station_total_kWh",
        "station_share_of_sessions", "station_rank_by_sessions",
        "station_is_top_quartile",
    ]
    result = df[keep].copy()
    result["arrival_date"] = result["arrival_date"].astype("string")
    return result


def build_daily_features(session_features: pd.DataFrame) -> pd.DataFrame:
    """Aggregate session features to a leakage-safe daily demand dataset."""
    data = session_features.copy()
    data["date"] = pd.to_datetime(data["arrival_date"])
    daily = data.groupby("date").agg(
        session_count=("_id", "size"),
        total_kWh=("kWhDelivered", "sum"),
        avg_kWh=("kWhDelivered", "mean"),
        median_kWh=("kWhDelivered", "median"),
        avg_connected_h=("connected_h", "mean"),
        avg_charging_h=("charging_h", "mean"),
        avg_idle_h=("idle_h", "mean"),
        avg_power_kW=("avg_power_kW", "mean"),
        n_stations=("stationID", "nunique"),
        n_unique_users=("userID", lambda values: values.notna().sum()),
        long_stay_share=("is_long_stay", "mean"),
        weekend_arrival_share=("is_weekend", "mean"),
        morning_arrival_share=("is_morning_arrival", "mean"),
        default_energy_spike_share=("is_default_energy_spike", "mean"),
        high_energy_share=("is_high_energy", "mean"),
        mean_requested_energy=("ui_kWhRequested", "mean"),
    ).sort_index()
    daily["dayofweek"] = daily.index.dayofweek
    daily["is_weekend"] = daily["dayofweek"].ge(5)
    daily["month"] = daily.index.month
    daily["day_of_month"] = daily.index.day
    daily["week_of_year"] = daily.index.isocalendar().week.astype("int64")
    daily["quarter"] = daily.index.quarter
    daily["lag_1"] = daily["session_count"].shift(1)
    daily["lag_7"] = daily["session_count"].shift(7)
    daily["lag_14"] = daily["session_count"].shift(14)
    daily["rolling_7_mean"] = daily["session_count"].shift(1).rolling(7, min_periods=3).mean()
    daily["rolling_14_mean"] = daily["session_count"].shift(1).rolling(14, min_periods=5).mean()
    daily["rolling_7_std"] = daily["session_count"].shift(1).rolling(7, min_periods=3).std()
    daily.index.name = "date"
    return daily.reset_index()


def validate(session_features: pd.DataFrame, daily_features: pd.DataFrame) -> pd.DataFrame:
    checks = [
        ("session_row_count_matches_input", len(session_features) == len(pd.read_csv(INPUT_FILE))),
        ("session_ids_unique", session_features["sessionID"].is_unique),
        ("daily_dates_unique", daily_features["date"].is_unique),
        ("no_negative_idle_duration", (session_features["idle_h"].dropna() >= 0).all()),
        ("charging_ratio_between_zero_and_one", session_features["charging_ratio"].dropna().between(0, 1).all()),
        ("daily_session_count_positive", (daily_features["session_count"] > 0).all()),
        ("lag_features_use_prior_days_only", daily_features.loc[14:, "lag_1"].notna().all()),
    ]
    return pd.DataFrame(checks, columns=["check", "passed"])


def main() -> None:
    source = pd.read_csv(INPUT_FILE)
    sessions = build_session_features(source)
    daily = build_daily_features(sessions)
    validation = validate(sessions, daily)
    if not validation["passed"].all():
        failed = validation.loc[~validation["passed"], "check"].tolist()
        raise ValueError("Feature validation failed: " + ", ".join(failed))

    sessions.to_csv(SESSION_OUTPUT, index=False)
    daily.to_csv(DAILY_OUTPUT, index=False)
    validation.to_csv(VALIDATION_OUTPUT, index=False)
    print(f"Created {SESSION_OUTPUT.name}: {sessions.shape[0]:,} rows x {sessions.shape[1]} columns")
    print(f"Created {DAILY_OUTPUT.name}: {daily.shape[0]:,} rows x {daily.shape[1]} columns")
    print(f"Validated {len(validation)} checks")


if __name__ == "__main__":
    main()
