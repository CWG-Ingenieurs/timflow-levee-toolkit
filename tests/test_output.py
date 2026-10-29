from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from openpyxl import load_workbook

import timflow_levee_toolkit as tlt
from timflow_levee_toolkit.output import _MAX_PATH, _fit_filename

PARTS = ["timflow", "Papendrecht West", "20260101_120000", "headX2", "run 51 storm event"]


def test_fit_filename_unchanged_when_short(tmp_path):
    assert _fit_filename(tmp_path, PARTS, ".pdf") == "_".join(PARTS) + ".pdf"


def test_fit_filename_shortened_to_path_limit(tmp_path):
    folder = tmp_path / ("f" * max(1, _MAX_PATH - len(str(tmp_path.resolve())) - 60))
    name = _fit_filename(folder, PARTS, ".pdf")
    assert name.endswith(".pdf")
    assert len(str(folder.resolve() / name)) <= _MAX_PATH
    assert not name.startswith("timflow_")  # the prefix is dropped first


def test_fit_filename_raises_when_folder_too_long(tmp_path):
    folder = tmp_path / ("f" * (_MAX_PATH - len(str(tmp_path.resolve())) - 10))
    with pytest.raises(OSError):
        _fit_filename(folder, PARTS, ".pdf")


def test_finalize_and_save_creates_folder_and_uses_file_label(tmp_path):
    folder = tmp_path / "not" / "yet"
    f, ax = plt.subplots()
    tlt.finalize_and_save(f, folder, "Project - Transect", modelrun="Run 1", tag="test",
                          show=False, file_label="Transect")
    footer = [t.get_text() for t in f.texts if t.get_text().startswith("Created with")]
    assert footer and footer[0].startswith(f"Created with timflow-levee-toolkit {tlt.__version__} on ")
    files = list(Path(folder).glob("*.pdf"))
    assert len(files) == 1
    assert files[0].name.startswith("timflow_Transect_") and files[0].name.endswith("_test_run 1.pdf")


def test_export_to_excel_round_trip_and_formats(tmp_path):
    df = pd.DataFrame({"rf": [0.123, 0.456], "lag": [1.25, 2.5]}, index=pd.Index(["a", "b"], name="obsloc"))
    path = tmp_path / "rf.xlsx"
    tlt.export_to_excel(df, path, number_formats={"rf": "0.0%"})
    pd.testing.assert_frame_equal(pd.read_excel(path, index_col=0), df)
    ws = load_workbook(path).active
    assert ws["B2"].number_format == "0.0%"
