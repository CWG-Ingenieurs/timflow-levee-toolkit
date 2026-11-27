"""Run the minimal path of the workflow notebooks on (a copy of) the example project, with the runner."""
import pandas as pd
import pytest

import timflow_levee_toolkit as tlt
from conftest import TRANSECT

SETUP = [
    "00 Set up project",
    "10 Import time series from Excel",
    "13 Piezometer locations",
    "20 Geohydrological scheme",
]
PERIOD = ("2025-12-01", "2025-12-08")  # the week of the example data

# Results of the example for Papendrecht West (timflow main, October 2026)
# The calibration of the example is not unique: several parameter sets fit about equally well, and
# differences in the last bit of the input (pandas version, platform) can lead to another of them
# (RMSE 0.08-0.10 m). So the test checks that the results make sense, not their exact values.
MAX_RMSE = 0.12  # [m]
LEAKAGE_FACTOR_RANGE = (10.0, 10_000.0)  # [m]


@pytest.mark.slow
def test_minimal_path_on_example(example_copy):
    assert tlt.run_notebooks(example_copy, SETUP, timeout=900) == []
    assert tlt.run_transects(example_copy, [TRANSECT], PERIOD, summary=False, timeout=900) == []
    executed = example_copy / "data" / "transects" / TRANSECT / "results_final" / "notebooks"
    assert (executed / "52 Timflow model.ipynb").exists()

    final = example_copy / "data" / "transects" / TRANSECT / "results_final"
    summary = pd.read_excel(final / "model_summary.xlsx", index_col=0).loc[TRANSECT]
    print(summary.to_string())
    assert 0 < summary["rmse_m"] < MAX_RMSE
    for key in ("leakage_factor_riverside_m", "leakage_factor_landside_m"):
        assert LEAKAGE_FACTOR_RANGE[0] < summary[key] < LEAKAGE_FACTOR_RANGE[1], key

    rf = pd.read_excel(final / "responsefactors.xlsx", index_col=0)
    assert len(rf) == 6
    assert rf["rf_steady_mod"].between(0, 1).all()
    print(rf.filter(like="_mod").to_string())
    # The shorter the change of the river level, the smaller the response:
    # a tide (hours) < a storm event (days) < steady
    assert (rf["rf_tidal_mod"] > 0).all()
    assert (rf["rf_tidal_mod"] < rf["rf_mhw_mod"]).all()
    assert (rf["rf_mhw_mod"] < rf["rf_steady_mod"]).all()
