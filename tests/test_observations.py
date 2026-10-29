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
