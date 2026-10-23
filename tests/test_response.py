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


def test_response_profile_at_toe_and_decay():
    lf, lh = 100.0, 1000.0
    rf = tlt.calculate_response_profile(np.array([0.0, lh]), lf, lh)
    assert rf[0] == pytest.approx(1 / (1 + lf / lh))
    assert rf[1] == pytest.approx(rf[0] * np.exp(-1))


def test_fit_response_profile_recovers_leakage_lengths():
    x = np.array([0.0, 20, 50, 100, 200, 400, 800])
    df = pd.DataFrame({
        "x_crosssection": x,
        "modellayer": 1,
        "rf_steady_mod": tlt.calculate_response_profile(x, 120.0, 900.0),
    })
    fit = tlt.fit_response_profile(df, "rf_steady_mod")
    assert fit["leakage_length_foreland"] == pytest.approx(120.0, rel=1e-4)
    assert fit["leakage_length_hinterland"] == pytest.approx(900.0, rel=1e-4)
    assert fit["r_squared"] == pytest.approx(1.0)
    assert fit["layer"] == 1


def test_fit_response_profile_lengths_are_positive():
    # Response that increases with x: an unbounded fit would give a negative leakage length
    df = pd.DataFrame({"x_crosssection": [0.0, 100, 200], "modellayer": 0, "rf": [0.2, 0.25, 0.3]})
    fit = tlt.fit_response_profile(df, "rf")
    assert fit["leakage_length_foreland"] >= 0
    assert fit["leakage_length_hinterland"] >= 0


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


def test_rf_mhw_takes_maximum_within_window():
    obslocs = obslocs_table()
    t = np.linspace(0, 10, 101)
    rf = np.where(np.abs(t - 5) <= 1, 0.6, 0.1)
    rf[t == 9.0] = 0.95  # outside the window around the peak: must be ignored
    rf_t = pd.DataFrame({(1, "far"): rf}, index=t)
    rf_t.columns = pd.MultiIndex.from_tuples(rf_t.columns, names=["layer", "obsloc"])
    df = tlt.calculate_rf_mhw(rf_t, obslocs, t_peak=5.0, window=1.0)
    assert df.loc["far", "rf_mhw_mod"] == pytest.approx(0.6)
    assert abs(df.loc["far", "t_mhw_mod"] - 5.0) <= 1.0
    assert df.loc["far", "x_crosssection"] == 50.0


def test_combine_rf_sorted_and_without_duplicate_columns():
    obslocs = obslocs_table()
    a = obslocs.assign(rf_steady_mod=[0.1, 0.9, 0.5])
    b = obslocs.assign(rf_tidal_mod=[0.05, 0.4, 0.2])
    df = tlt.combine_rf(obslocs, a, b)
    assert list(df.columns) == ["x_crosssection", "modellayer", "rf_steady_mod", "rf_tidal_mod"]
    assert list(df.index) == ["toe_shallow", "toe_deep", "far"]
    assert df.index.name == "obsloc"
