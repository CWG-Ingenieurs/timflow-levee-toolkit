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
EXPECTED = {
    "rmse_m": 0.1002,
    "leakage_length_foreland_steady_m": 144.5,
    "leakage_length_hinterland_steady_m": 1618.0,
}


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
    assert summary["rmse_m"] == pytest.approx(EXPECTED["rmse_m"], abs=0.005)
    for key in ("leakage_length_foreland_steady_m", "leakage_length_hinterland_steady_m"):
        assert summary[key] == pytest.approx(EXPECTED[key], rel=0.02), key

    rf = pd.read_excel(final / "responsefactors.xlsx", index_col=0)
    assert len(rf) == 6
    assert rf["rf_steady_mod"].between(0, 1).all()
