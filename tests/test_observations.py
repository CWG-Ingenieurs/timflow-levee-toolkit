from datetime import datetime as dt

import numpy as np
import pandas as pd
import pytest

import timflow_levee_toolkit as tlt


def test_observations_round_trip(tmp_path):
    start, end = dt(2025, 12, 1), dt(2025, 12, 8)
    times = pd.DatetimeIndex(["2025-12-01 00:00:00", "2025-12-01 00:04:56", "2025-12-01 00:10:00",
                              "2025-12-03 13:37:12", "2025-12-07 23:59:59"])
    obs = pd.DataFrame({
        "river": [0.123456789012345, np.nan, 1.1, -0.05, 0.3],
        "piezo_1": [np.nan, -1.84312345678901, np.nan, -1.85, -1.9],
    }, index=tlt.to_days(times, start))
    obs["polder_level"] = -1.92

    path = tmp_path / "observations_model_period.xlsx"
    tlt.write_observations(obs, path, start, end)
    back = tlt.read_observations(path)

    np.testing.assert_allclose(back.index.to_numpy(), obs.index.to_numpy(), rtol=1e-15, atol=1e-15)  # model time
    assert np.array_equal(back.to_numpy(), obs.to_numpy(), equal_nan=True)  # bit-exact heads
    assert list(back.columns) == list(obs.columns) and back.index.name == "Time [days]"
    assert back.attrs == {"start": pd.Timestamp(start), "end": pd.Timestamp(end)}
    # In Excel: date and time, and the model time in days since the start
    sheet = pd.read_excel(path, sheet_name="observations")
    assert list(sheet.columns[:2]) == ["time", "days since start"]
    assert sheet["time"].iloc[1] == pd.Timestamp("2025-12-01 00:04:56")
    assert sheet["days since start"].iloc[1] == pytest.approx(296 / 86400)


def _tide_with_trend(drop):
    t = np.arange(0, 7, 10 / 1440)
    return pd.Series(np.sin(2 * np.pi * t / (12.42 / 24)) - drop * t / 7, index=pd.Index(t, name="Time [days]"))


def test_check_trend_warns_for_a_trend():
    obs = pd.DataFrame({"river": _tide_with_trend(0.6), "calm": _tide_with_trend(0.0)})
    obs["polder_level"] = -1.92
    with pytest.warns(UserWarning, match="Trend in the model period.*river"):
        table = tlt.check_trend(obs)
    assert table.loc["river", "change"] == pytest.approx(0.6 * 6 / 7, abs=0.02)  # without the half windows
    assert table.loc["calm", "change"] < 0.05  # 25 hours is not exactly two tidal periods
    assert table.loc["polder_level", "change"] == 0
    assert list(table["trend"]) == [True, False, False]


def test_check_trend_no_warning_without_trend(recwarn):
    table = tlt.check_trend(pd.DataFrame({"calm": _tide_with_trend(0.0)}))
    assert not table["trend"].any()
    assert not [w for w in recwarn if "Trend" in str(w.message)]
