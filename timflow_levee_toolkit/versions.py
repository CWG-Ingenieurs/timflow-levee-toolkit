"""Versions of the toolkit and its dependencies, for the record in executed notebooks."""
from importlib import metadata
from importlib.util import find_spec
from pathlib import Path

# Dependencies of the toolkit that `timflow.show_versions` does not print
PACKAGES = ("pastastore", "geopandas", "contextily")
# Optional dependencies, for the download notebooks (11, 12) and the subsurface data (21)
OPTIONAL = ("hydropandas", "nlmod", "brodata")


def _version(name):
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "Not Installed"


def show_versions(optional=True) -> None:
    """Print the version of the toolkit and its dependencies, in the style of `timflow.show_versions`.

    First the version of the toolkit and the folders of the toolkit and timflow, which show the
    copy a notebook uses (a local clone or an installed release); then `timflow.show_versions()`
    (Python, numpy, scipy, pandas, matplotlib, lmfit, ...); then the other dependencies.

    Parameters
    ----------
    optional : bool, optional
        Print the version of optional dependencies (hydropandas, nlmod, brodata), by default True
    """
    import timflow

    from . import __version__

    print(
        f"Toolkit version    : {__version__}\n"
        f"Toolkit location   : {Path(__file__).resolve().parent}\n"
        f"timflow location   : {Path(find_spec('timflow').origin).parent}\n"
    )
    timflow.show_versions()
    names = PACKAGES + (OPTIONAL if optional else ())
    print("\n".join(f"{f'{name.capitalize()} version':<19}: {_version(name)}" for name in names))
