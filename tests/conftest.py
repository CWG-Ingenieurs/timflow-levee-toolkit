import shutil
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "papendrecht"
TRANSECT = "Papendrecht West"


@pytest.fixture
def example_dir():
    """The example project (read only: use `example_copy` to write)."""
    return EXAMPLE


@pytest.fixture
def example_copy(tmp_path):
    """A copy of the input files of the example project, to write in."""
    target = tmp_path / "papendrecht"
    shutil.copytree(EXAMPLE, target, ignore=shutil.ignore_patterns(
        "pastastore", "timeseries", "results*", "subsurface", "project_data.gpkg", "piezometers_from_bro.xlsx"))
    return target


@pytest.fixture
def transient_model(example_dir):
    """Transient cross-section model of the example transect, with the parameters of the scheme."""
    import timflow as tf

    import timflow_levee_toolkit as tlt

    params, naq = tlt.read_model_params(
        example_dir / "data" / "transects" / TRANSECT / f"model_parameters_{TRANSECT}.xlsx", "initial")
    ml = tf.transient.ModelXsection(naq=naq, tmin=1e-5, tmax=1e2)
    bounds = {"river": (-np.inf, -16), "foreland": (-16, 0), "hinterland": (0, np.inf)}
    for zone, (x1, x2) in bounds.items():
        p = params[zone]
        tf.transient.XsectionMaq(
            ml, x1=x1, x2=x2, kaq=p["kaq"], z=p["z"], Saq=p["Saq"], Sll=p["Sll"], c=p["c"],
            leffaq=p["leffaq"], leffll=p["leffll"], topboundary="semi",
            tsandhstar=[(0, 1.0)] if zone == "river" else None, name=zone,
        )
    return ml
