"""Versions of the toolkit, Python and the main packages, for the record in executed notebooks."""
import importlib.util
import platform
import sys
from importlib import metadata
from pathlib import Path

PACKAGES = ("pastastore", "pandas", "numpy", "scipy", "matplotlib", "geopandas", "hydropandas", "nlmod", "brodata")


def show_versions():
    """Print the version and location of the toolkit, and the versions of Python and the main packages.

    The locations show which copy of the toolkit and of timflow the notebook uses (e.g. a local
    clone or an installed release). Packages that are not installed are left out.
    """
    from . import __version__

    timflow = importlib.util.find_spec("timflow")
    lines = [
        f"timflow-levee-toolkit version {__version__}",
        f"  installed at: {Path(__file__).resolve().parent}",
        f"Python {platform.python_version()} ({sys.executable})",
    ]
    if timflow is not None:
        lines.append(f"timflow {metadata.version('timflow')} ({Path(timflow.origin).parent})")
    others = []
    for name in PACKAGES:
        try:
            others.append(f"{name} {metadata.version(name)}")
        except metadata.PackageNotFoundError:
            pass
    lines.append("Other packages: " + ", ".join(others))
    print("\n".join(lines))
