import contextily
import matplotlib.pyplot as plt
import pandas as pd
import pytest

import timflow_levee_toolkit as tlt
from conftest import TRANSECT


@pytest.fixture(autouse=True)
def no_tiles(monkeypatch):
    """No background tiles in the unit tests."""
    monkeypatch.setattr(contextily, "add_basemap", lambda ax, **kwargs: None)


def test_crosssection_from_metadata(example_dir):
    line = tlt.load_project(example_dir).crosssection(TRANSECT)
    (x1, y1), (x2, y2) = line
    assert x1 < x2  # river side first (west of the hinterland in this transect)
    assert all(isinstance(v, float) for v in (x1, y1, x2, y2))


def test_crosssection_missing_is_none(example_copy):
    path = example_copy / "data" / "general" / "transects_metadata.xlsx"
    metadata = pd.read_excel(path, sheet_name="transects").drop(columns=["x1_xsec", "y1_xsec", "x2_xsec", "y2_xsec"])
    metadata.to_excel(path, sheet_name="transects", index=False)
    assert tlt.load_project(example_copy).crosssection(TRANSECT) is None


def test_plot_transect_map_one_label_per_well():
    piezometers = pd.DataFrame({
        "name": ["W1_1", "W1_2", "W2_1"],
        "x": [100.0, 100.0, 160.0],  # W1 has two filters at the same location
        "y": [200.0, 200.0, 180.0],
        "x_crosssection": [0.0, 0.0, 65.0],
    })
    f, ax = tlt.plot_transect_map(piezometers, line=[(50.0, 230.0), (250.0, 150.0)], title="T")
    labels = sorted(t.get_text() for t in ax.texts)
    assert labels == ["W1\nx = 0 m", "W2\nx = 65 m"]
    assert [t.get_text() for t in ax.get_legend().get_texts()] == ["cross-section", "start (river side)", "piezometers"]
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    assert x0 < 50 and x1 > 250 and y0 < 150 and y1 > 230  # line and piezometers inside the map
    plt.close(f)


def test_plot_transect_map_without_line():
    piezometers = pd.DataFrame({"name": ["W1_1"], "x": [0.0], "y": [0.0], "x_crosssection": [10.0]})
    f, ax = tlt.plot_transect_map(piezometers)
    assert [t.get_text() for t in ax.get_legend().get_texts()] == ["piezometers"]
    plt.close(f)
