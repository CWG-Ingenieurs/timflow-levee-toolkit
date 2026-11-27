"""Runner (filling in and executing the workflow notebooks) and new projects (create_project)."""
import sqlite3

import numpy as np
import pandas as pd
import pytest

import timflow_levee_toolkit as tlt
from conftest import TRANSECT


def code(nb):
    return "\n".join(c.source for c in nb.cells if c.cell_type == "code")


def test_prepare_notebook_fills_in_project_and_transect(tmp_path):
    nb = tlt.prepare_notebook("52 Timflow model", tmp_path, TRANSECT)
    source = code(nb)
    assert f'project_dir = Path(r"{tmp_path.resolve()}")' in source
    assert f'transect_name = "{TRANSECT}"' in source
    assert 'Path.cwd().parent / "examples"' not in source


def test_prepare_notebook_without_project_dir_keeps_the_example():
    nb = tlt.prepare_notebook("00 Set up project", None)
    assert 'project_dir = Path.cwd().parent / "examples" / "papendrecht"' in code(nb)


def test_prepare_notebook_lines_cells_and_insert(tmp_path):
    nb = tlt.prepare_notebook(
        "51 Prepare model inputs", tmp_path, TRANSECT,
        lines={"xlim = [dt(": "xlim = [dt(2026, 1, 30), dt(2026, 2, 6)]"},
        insert_after={'"heads_model_period.png"': "extra = 1"},
    )
    source = code(nb)
    assert "xlim = [dt(2026, 1, 30), dt(2026, 2, 6)]" in source
    cells = [c.source for c in nb.cells if c.cell_type == "code"]
    i = cells.index("extra = 1")
    assert '"heads_model_period.png"' in cells[i - 1]

    nb = tlt.prepare_notebook("52 Timflow model", tmp_path, TRANSECT, cells={"cal.set_aquifer_parameter(": "pass  # mine"})
    assert "pass  # mine" in code(nb)
    assert "cal.set_aquifer_parameter(" not in code(nb)


def test_prepare_notebook_reports_a_changed_notebook(tmp_path):
    with pytest.raises(ValueError, match="cells with"):
        tlt.prepare_notebook("51 Prepare model inputs", tmp_path, lines={"no such line": "x = 1"})


def test_run_transects_checks_its_input(example_dir):
    with pytest.raises(ValueError, match="model period"):
        tlt.run_transects(example_dir, [TRANSECT])
    with pytest.raises(ValueError, match="Unknown transects"):
        tlt.run_transects(example_dir, ["no such transect"], ("2025-12-01", "2025-12-08"))


def test_create_project(tmp_path):
    project = tlt.create_project(tmp_path / "new", name="New project")
    assert project.name == "New project"
    assert project.metadata().empty
    general = project.general_dir
    for name in ("transects_metadata.xlsx", "piezometers.xlsx", "timeseries.xlsx", "model_parameters_TEMPLATE.xlsx"):
        assert (general / name).exists(), name
    assert pd.read_excel(general / "piezometers.xlsx").empty
    assert list(pd.read_excel(general / "timeseries.xlsx").columns) == ["datetime"]
    assert "explanation" in pd.ExcelFile(general / "transects_metadata.xlsx").sheet_names
    assert (general / "storm_events").is_dir() and (project.root / "data" / "transects").is_dir()
    run_py = (project.root / "run.py").read_text(encoding="utf-8")
    compile(run_py, "run.py", "exec")
    assert "'New project'" in run_py

    with pytest.raises(FileExistsError):
        tlt.create_project(tmp_path / "new")


def test_write_river_gauges_merges_and_styles(tmp_path):
    gpkg = tmp_path / "project_data.gpkg"
    tlt.write_piezometers(pd.DataFrame({"name": ["P1"], "transect": ["T"], "x": [1.0], "y": [2.0]}), gpkg)
    tlt.write_river_gauges(pd.DataFrame({"name": ["A", "B"], "x": [10.0, 20.0], "y": [5.0, 5.0], "transects": "T"}), gpkg)
    gdf = tlt.write_river_gauges(pd.DataFrame({"name": ["B", "C"], "x": [21.0, 30.0], "y": [5.0, 5.0], "transects": "U"}), gpkg)
    assert sorted(gdf["name"]) == ["A", "B", "C"]
    assert gdf.set_index("name").loc["B", "x"] == 21.0  # updated
    with sqlite3.connect(gpkg) as conn:
        styles = dict(conn.execute("SELECT f_table_name, styleQML FROM layer_styles WHERE useAsDefault = 1"))
    assert set(styles) == {"piezometers", "river_gauges"}
    assert 'value="triangle"' in styles["river_gauges"] and 'value="circle"' in styles["piezometers"]


def hourly(days=60):
    t = pd.date_range("2026-01-01", periods=days * 24, freq="h")
    tide = 0.5 * np.sin(2 * np.pi * np.arange(len(t)) / 12.42)
    frac = ((t - pd.Timestamp("2026-02-10")) / pd.Timedelta(days=10)).to_numpy(dtype=float)
    wave = np.where((frac > 0) & (frac < 1), 2.0 * np.sin(np.pi * np.clip(frac, 0, 1)), 0.0)
    return pd.DataFrame({"R": tide + wave}, index=t), pd.DataFrame({"T: P": 0.3 * tide + 0.5 * wave}, index=t)


def test_candidate_model_periods_tide_avoids_the_wave():
    rivers, heads = hourly()
    periods = tlt.candidate_model_periods(rivers, heads, mode="tide", n_best=3)
    best = periods.dropna(subset=["rank"]).sort_values("rank")
    assert len(best) == 3
    assert (best["river_change"] < 0.1).all()
    assert not ((best.index < "2026-02-20") & (best["end"] > "2026-02-10")).any()


def test_candidate_model_periods_wave_finds_the_wave():
    rivers, heads = hourly()
    periods = tlt.candidate_model_periods(rivers, heads, mode="wave", n_best=2)
    best = periods.dropna(subset=["rank"]).sort_values("rank")
    assert best["river_change"].iloc[0] > 1.5
    assert best.index[0] < pd.Timestamp("2026-02-20") and best["end"].iloc[0] > pd.Timestamp("2026-02-10")


def test_candidate_model_periods_needs_complete_data():
    rivers, heads = hourly()
    heads.loc["2026-01-01":"2026-02-28", "T: P"] = np.nan
    periods = tlt.candidate_model_periods(rivers, heads, mode="tide")
    assert periods["rank"].dropna().empty
    with pytest.raises(ValueError, match="mode"):
        tlt.candidate_model_periods(rivers, heads, mode="flood")
