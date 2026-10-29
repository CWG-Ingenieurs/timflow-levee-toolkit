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
    assert out.startswith(f"timflow-levee-toolkit version {tlt.__version__}\n")
    assert "installed at:" in out and "\nPython 3." in out and "\ntimflow " in out and "pandas " in out
