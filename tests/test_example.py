"""Run the minimal path of the workflow notebooks on (a copy of) the example project."""
import nbformat
import pandas as pd
import pytest
from nbclient import NotebookClient

from conftest import REPO, TRANSECT

NOTEBOOKS = [
    "00 Set up project",
    "01 Piezometer locations",
    "10 Import time series from Excel",
    "20 Geohydrological scheme",
    "51 Prepare model inputs",
    "52 Timflow model",
]
PROJECT_DIR_LINE = 'project_dir = Path.cwd().parent / "examples" / "papendrecht"'

# Results of the example for Papendrecht West (timflow main, October 2026)
# The calibration of the example is not unique: several parameter sets fit about equally well, and
# differences in the last bit of the input (pandas version, platform) can lead to another of them
# (RMSE 0.08-0.10 m). So the test checks that the results make sense, not their exact values.
MAX_RMSE = 0.12  # [m]
LEAKAGE_LENGTH_RANGE = (10.0, 10_000.0)  # [m]


def run_notebook(name, project_dir):
    nb = nbformat.read(REPO / "notebooks" / f"{name}.ipynb", as_version=4)
    cells = [c for c in nb.cells if c.cell_type == "code" and PROJECT_DIR_LINE in c.source]
    assert len(cells) == 1, f"{name}: project_dir cell not found"
    cells[0].source = cells[0].source.replace(PROJECT_DIR_LINE, f"project_dir = Path(r'{project_dir}')")
    for cell in nb.cells:
        if "parameters" in cell.metadata.get("tags", []):
            cell.source = f'transect_name = "{TRANSECT}"'
    NotebookClient(nb, timeout=900, kernel_name="python3",
                   resources={"metadata": {"path": str(REPO / "notebooks")}}).execute()


@pytest.mark.slow
def test_minimal_path_on_example(example_copy):
    for name in NOTEBOOKS:
        run_notebook(name, example_copy)

    final = example_copy / "data" / "transects" / TRANSECT / "results_final"
    summary = pd.read_excel(final / "model_summary.xlsx", index_col=0).loc[TRANSECT]
    print(summary.to_string())
    assert 0 < summary["rmse_m"] < MAX_RMSE
    for key in ("leakage_length_foreland_steady_m", "leakage_length_hinterland_steady_m",
                "leakage_length_foreland_mhw_m", "leakage_length_hinterland_mhw_m"):
        assert LEAKAGE_LENGTH_RANGE[0] < summary[key] < LEAKAGE_LENGTH_RANGE[1], key
    assert summary["r_squared_steady"] > 0.9

    rf = pd.read_excel(final / "responsefactors.xlsx", index_col=0)
    assert len(rf) == 6
    assert rf["rf_steady_mod"].between(0, 1).all()
    print(rf.filter(like="_mod").to_string())
    # The shorter the change of the river level, the smaller the response:
    # a tide (hours) < a storm event (days) < steady
    assert (rf["rf_tidal_mod"] > 0).all()
    assert (rf["rf_tidal_mod"] < rf["rf_mhw_mod"]).all()
    assert (rf["rf_mhw_mod"] < rf["rf_steady_mod"]).all()
