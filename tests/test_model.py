import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook

import timflow_levee_toolkit as tlt
from conftest import TRANSECT
from timflow_levee_toolkit.model import _unique_tab_name


def parameter_file(project_dir):
    return project_dir / "data" / "transects" / TRANSECT / f"model_parameters_{TRANSECT}.xlsx"


def test_read_model_params(example_dir):
    params, naq = tlt.read_model_params(parameter_file(example_dir), "initial")
    assert naq == 2
    assert set(params) == {"river", "foreland", "hinterland"}
    assert len(params["river"]["z"]) == 2 * naq + 1
    tlt.validate_model_params(params, naq)


def test_validate_model_params_finds_problems(example_dir):
    params, naq = tlt.read_model_params(parameter_file(example_dir), "initial")
    params["foreland"]["kaq"] = [-1.0, *params["foreland"]["kaq"][1:]]
    params["river"]["leffaq"] = [0.0, 1.5]
    with pytest.raises(ValueError) as error:
        tlt.validate_model_params(params, naq)
    assert "foreland: 'kaq' must be positive" in str(error.value)
    assert "river: 'leffaq' must be between 0 and 1" in str(error.value)


def test_write_and_read_model_params_round_trip(example_copy, transient_model):
    path = parameter_file(example_copy)
    written = tlt.write_model_params(transient_model, path, tab_name="calibrated")
    assert written.attrs["tab_name"] == "calibrated"
    original, naq = tlt.read_model_params(path, "initial")
    again, _ = tlt.read_model_params(path, "calibrated")
    for zone in original:
        for key in ("z", "kaq", "c", "Saq", "Sll"):
            np.testing.assert_allclose(again[zone][key], original[zone][key], err_msg=f"{zone} {key}")

    # A second write never overwrites: the tab name gets a timestamp
    second = tlt.write_model_params(transient_model, path, tab_name="calibrated")
    assert second.attrs["tab_name"].startswith("calibrated_")
    assert {"initial", "calibrated", second.attrs["tab_name"]} <= set(load_workbook(path).sheetnames)


def test_unique_tab_name():
    assert _unique_tab_name("calibrated", ["initial"]) == "calibrated"
    name = _unique_tab_name("Calibrated", ["calibrated"])
    assert name.startswith("Calibrated_") and len(name) <= 31
    long_name = _unique_tab_name("x" * 31, ["x" * 31])
    assert len(long_name) <= 31


def test_create_parameter_template(tmp_path):
    path = tmp_path / "model_parameters_new.xlsx"
    tlt.create_parameter_template(path, naq=3)
    template = pd.read_excel(path, sheet_name="initial")
    assert len(template) == 3 * 3
    assert set(template["inhomogeneity_id"]) == {"river", "foreland", "hinterland"}
    with pytest.raises(FileExistsError):
        tlt.create_parameter_template(path)


def test_read_storm_event(example_dir):
    path = example_dir / "data" / "general" / "storm_events" / "storm_event_308113.xlsx"
    storm = tlt.read_storm_event(path, h_river_avg=1.0)
    assert storm.index.name == "time"
    assert storm.index[0] == 0
    assert list(storm.columns) == ["t_original", "h_river", "h_river_rel"]
    np.testing.assert_allclose(storm["h_river_rel"], storm["h_river"] - 1.0)
    assert storm["h_river"].max() > 3  # a storm: well above the average river level


def test_to_tsandhstar_uses_step_averages():
    series = pd.Series([0.0, 2.0, np.nan, 4.0], index=[0.0, 0.1, 0.2, 0.3])
    assert tlt.to_tsandhstar(series) == [(0.0, 1.0), (0.1, 3.0)]
