import re

import timflow_levee_toolkit as tlt
from conftest import REPO


def test_version_badge_matches_package_version():
    """The version badge in the README is static: update it together with `__version__`."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    badge = re.search(r"img\.shields\.io/badge/version-([^-]+)-", readme)
    assert badge, "version badge not found in README.md"
    assert badge.group(1) == tlt.__version__


def test_show_versions(capsys):
    tlt.show_versions()
    out = capsys.readouterr().out
    assert out.startswith(f"Toolkit version    : {tlt.__version__}\n")
    assert "Toolkit location   : " in out and "timflow location   : " in out
    # timflow.show_versions() for timflow and its dependencies, then the other dependencies, each once
    assert out.count("timflow version    : ") == 1 and out.count("Pandas version     : ") == 1
    assert "Pastastore version : " in out
