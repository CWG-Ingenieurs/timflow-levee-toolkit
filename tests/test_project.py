import pandas as pd
import pytest

import timflow_levee_toolkit as tlt
from conftest import TRANSECT


def test_load_example_project(example_dir):
    project = tlt.load_project(example_dir)
    assert project.name == "Papendrecht example"
    assert project.transects() == ["Papendrecht West", "Papendrecht East"]
    assert project.units["head"] == "m NAP"
    assert project.parameters_file(TRANSECT).exists()
    assert project.transect_dir(TRANSECT, "final") == example_dir / "data" / "transects" / TRANSECT / "results_final"


def test_load_project_without_settings_uses_defaults(tmp_path):
    project = tlt.load_project(tmp_path)
    assert project.general_dir == tmp_path / "data" / "general"
    assert project.units == tlt.DEFAULT_SETTINGS["units"]


def test_create_folders(example_copy):
    project = tlt.load_project(example_copy)
    project.create_folders()
    assert project.transect_dir("Papendrecht East", "intermediate").is_dir()
    assert project.results_dir.parent == example_copy


def test_read_transect_metadata(example_dir):
    project = tlt.load_project(example_dir)
    meta = project.transect_metadata(TRANSECT)
    assert meta["loc_river"] == "dordrecht"
    assert meta["farfield"] == "polder_level"
    assert meta["L_river"] > 0 and meta["L_foreland"] > 0
    assert "tmin" not in meta and "tmax" not in meta  # the model period is chosen in notebook 51


def test_metadata_problems_are_reported(example_dir):
    metadata = tlt.load_project(example_dir).metadata()
    assert tlt.validate_transects_metadata(metadata) == []
    problems = tlt.validate_transects_metadata(metadata.drop(columns="width_river"))
    assert any("width_river" in p for p in problems)
    with pytest.raises(ValueError, match="width_river"):
        tlt.validate_transects_metadata(metadata.drop(columns="width_river"), raise_errors=True)


def test_empty_required_metadata_raises_for_that_transect(example_copy):
    path = example_copy / "data" / "general" / "transects_metadata.xlsx"
    metadata = pd.read_excel(path, sheet_name="transects")
    metadata.loc[metadata["transect"] == "Papendrecht East", "polder_level"] = None
    metadata.to_excel(path, sheet_name="transects", index=False)
    assert tlt.read_transect_metadata(path, TRANSECT)["polder_level"] is not None
    with pytest.raises(ValueError, match="polder_level"):
        tlt.read_transect_metadata(path, "Papendrecht East")


def test_read_piezometer_table(example_dir):
    project = tlt.load_project(example_dir)
    table = tlt.read_piezometer_table(project.general_file("piezometers"))
    assert len(table) == 12
    assert set(tlt.PIEZOMETERS_REQUIRED) <= set(table.columns)
    assert table.set_index("name").loc["GMW000000112235_1", "use_calibration"] == 0
    assert table["use_calibration"].isin([0, 1]).all()


def test_piezometer_table_of_one_transect(example_dir):
    project = tlt.load_project(example_dir)
    table = project.piezometer_table(TRANSECT)
    assert len(table) == 6
    assert (table["transect"] == TRANSECT).all()
    assert len(project.piezometer_table()) == 12


def test_add_piezometers_keeps_existing_rows(example_copy):
    from openpyxl import load_workbook

    path = tlt.load_project(example_copy).general_file("piezometers")
    before = pd.read_excel(path, sheet_name="piezometers")
    downloaded = pd.DataFrame({
        "name": ["GMW000000112214_1", "NEW_1", "NEW_1"],  # one that is there, a new one twice
        "transect": TRANSECT,
        "x": [0.0, 105800.0, 105800.0],
        "y": [0.0, 427400.0, 427400.0],
        "screen_top": [99.0, -13.0, -13.0],
        "screen_bottom": [98.0, -15.0, -15.0],
        "modellayer": None,
        "x_crosssection": None,
        "use_calibration": 1,
        "tube_nr": [1, 1, 1],  # not a column of the table: left out
    })
    added = tlt.add_piezometers(path, downloaded)
    assert added["name"].tolist() == ["NEW_1"]
    assert "tube_nr" not in added.columns

    after = pd.read_excel(path, sheet_name="piezometers")
    assert len(after) == len(before) + 1
    # filled-in rows unchanged (an empty modellayer in the new row makes the column float)
    pd.testing.assert_frame_equal(after.iloc[:len(before)], before, check_dtype=False)
    new = after.set_index("name").loc["NEW_1"]
    assert new["screen_top"] == -13.0 and pd.isna(new["modellayer"])
    assert "explanation" in load_workbook(path).sheetnames

    # nothing new: the file is not written again
    mtime = path.stat().st_mtime_ns
    assert tlt.add_piezometers(path, downloaded).empty
    assert path.stat().st_mtime_ns == mtime


def test_check_piezometer_table(example_dir):
    project = tlt.load_project(example_dir)
    assert tlt.check_piezometer_table(project.piezometer_table()).empty  # the example is complete

    table = pd.DataFrame({
        "name": ["ok", "no_x", "no_layer", "bad_layer", "bad_use"],
        "transect": "T",
        "screen_top": -13.0,
        "screen_bottom": -15.0,
        "x_crosssection": [10.0, None, 10.0, 10.0, 10.0],
        "modellayer": [0, 0, None, 0.5, 1],
        "use_calibration": [1, 1, 0, 1, 2],
    })
    problems = tlt.check_piezometer_table(table).set_index("name")["problem"]
    assert problems.index.tolist() == ["no_x", "no_layer", "bad_layer", "bad_use"]
    assert problems["no_x"] == "x_crosssection is empty"
    assert problems["no_layer"] == "modellayer is empty"
    assert "not a whole number" in problems["bad_layer"]
    assert "not 0 or 1" in problems["bad_use"]


def test_add_piezometers_creates_table(tmp_path):
    path = tmp_path / "piezometers.xlsx"
    added = tlt.add_piezometers(path, pd.DataFrame({"name": ["P1"], "transect": ["T"], "x": [1.0], "y": [2.0]}))
    assert len(added) == 1
    table = pd.read_excel(path, sheet_name="piezometers")
    assert table.columns.tolist() == tlt.PIEZOMETERS_COLUMNS
    assert table.loc[0, "name"] == "P1"


def test_make_obslocs(example_dir):
    project = tlt.load_project(example_dir)
    table = tlt.read_piezometer_table(project.general_file("piezometers"))
    obslocs = tlt.make_obslocs(table[table["transect"] == TRANSECT])
    assert obslocs.index.name == "name"
    assert {"x_crosssection", "modellayer", "use_calibration"} <= set(obslocs.columns)
    with pytest.raises(KeyError, match="modellayer"):
        tlt.make_obslocs(table.drop(columns="modellayer"))


def test_make_obslocs_without_modellayer(capsys):
    piezometers = pd.DataFrame({
        "name": ["deep", "shallow", "no_x"],
        "x_crosssection": [10.0, 10.0, None],
        "modellayer": [0.0, None, 0.0],
        "use_calibration": [1, 0, 1],
    })
    obslocs = tlt.make_obslocs(piezometers)
    assert obslocs.index.tolist() == ["deep"]
    assert "shallow" in capsys.readouterr().out
