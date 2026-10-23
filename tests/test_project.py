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
    assert meta["tmin"] == pd.Timestamp("2025-12-01")


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


def test_make_obslocs(example_dir):
    project = tlt.load_project(example_dir)
    table = tlt.read_piezometer_table(project.general_file("piezometers"))
    obslocs = tlt.make_obslocs(table[table["transect"] == TRANSECT])
    assert obslocs.index.name == "name"
    assert {"x_crosssection", "modellayer", "use_calibration"} <= set(obslocs.columns)
    with pytest.raises(KeyError, match="modellayer"):
        tlt.make_obslocs(table.drop(columns="modellayer"))
