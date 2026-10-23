import re

import timflow_levee_toolkit as tlt
from conftest import REPO


def test_version_badge_matches_package_version():
    """The version badge in the README is static: update it together with `__version__`."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    badge = re.search(r"img\.shields\.io/badge/version-([^-]+)-", readme)
    assert badge, "version badge not found in README.md"
    assert badge.group(1) == tlt.__version__
