import numpy as np
import pandas as pd
import pytest

import timflow_levee_toolkit as tlt

TIDE = 12.42 / 24  # tidal period [days]


def tidal_series(amplitude=1.0, lag=0.0, days=5.0, dt=10 / 1440):
    t = np.arange(0, days, dt)
    return pd.Series(amplitude * np.sin(2 * np.pi * (t - lag) / TIDE), index=t)


def obslocs_table():
    return pd.DataFrame(
        {"x_crosssection": [50.0, 0.0, 0.0], "modellayer": [1, 1, 0]},
        index=pd.Index(["far", "toe_deep", "toe_shallow"], name="name"),
    )


def test_rf_peaks_amplitude_and_lag():
    lag = 6 * 10 / 1440  # one hour, a multiple of the time step
    river = tidal_series()
    heads = pd.DataFrame({"piezo": tidal_series(amplitude=0.4, lag=lag)})
    peaks = tlt.calculate_rf_peaks(heads, river)
    assert len(peaks) >= 9
    assert peaks["response_factor"].median() == pytest.approx(0.4, abs=1e-3)
    assert peaks["t_offset"].median() == pytest.approx(lag, abs=1e-9)


def test_summarize_rf_tidal_medians_per_location():
    obslocs = obslocs_table()
    peaks = pd.DataFrame({
        "obsloc": ["far", "far", "far", "toe_deep"],
        "response_factor": [0.1, 0.2, 0.9, 0.5],
        "t_offset": [1 / 24, 2 / 24, 3 / 24, 0.0],
    })
    df = tlt.summarize_rf_tidal({"mod": peaks}, obslocs)
    assert df.loc["far", "rf_tidal_mod"] == pytest.approx(0.2)
    assert df.loc["far", "lag_tidal_mod_hours"] == pytest.approx(2.0)
    assert df.loc["far", "n_peaks_mod"] == 3
    assert np.isnan(df.loc["toe_shallow", "rf_tidal_mod"])


def test_rf_mhw_is_peak_head_over_peak_river():
    obslocs = obslocs_table()
    t = np.linspace(0, 10, 101)
    h_river = pd.Series(np.interp(t, [0, 5, 10], [0.0, 2.0, 0.0]), index=t)
    # The head lags behind the river: after the river peak, h / h_river exceeds the peak ratio
    h = pd.DataFrame({(1, "far"): np.interp(t, [0, 6, 10], [0.0, 1.2, 0.6])}, index=t)
    h.columns = pd.MultiIndex.from_tuples(h.columns, names=["layer", "obsloc"])
    df = tlt.calculate_rf_mhw(h, h_river, obslocs)
    assert df.loc["far", "rf_mhw_mod"] == pytest.approx(0.6)
    assert df.loc["far", "t_mhw_mod"] == pytest.approx(6.0)
    assert df.loc["far", "x_crosssection"] == 50.0


def test_combine_rf_profiles_long_table():
    x = np.array([0.0, 50.0])
    steady = pd.DataFrame({0: [0.5, 0.1], 1: [0.9, 0.8]}, index=pd.Index(x, name="x [m]"))
    steady.columns.name = "layer"
    mhw = steady * 0.9
    df = tlt.combine_rf_profiles({"rf_steady_mod": steady, "rf_mhw_mod": mhw})
    assert list(df.columns) == ["layer", "x [m]", "rf_steady_mod", "rf_mhw_mod"]
    assert list(df["layer"]) == [0, 0, 1, 1]
    assert list(df["x [m]"]) == [0.0, 50.0, 0.0, 50.0]
    assert df.loc[(df["layer"] == 1) & (df["x [m]"] == 50.0), "rf_mhw_mod"].item() == pytest.approx(0.72)


def test_combine_rf_sorted_and_without_duplicate_columns():
    obslocs = obslocs_table()
    a = obslocs.assign(rf_steady_mod=[0.1, 0.9, 0.5])
    b = obslocs.assign(rf_tidal_mod=[0.05, 0.4, 0.2])
    df = tlt.combine_rf(obslocs, a, b)
    assert list(df.columns) == ["x_crosssection", "modellayer", "rf_steady_mod", "rf_tidal_mod"]
    assert list(df.index) == ["toe_shallow", "toe_deep", "far"]
    assert df.index.name == "obsloc"
