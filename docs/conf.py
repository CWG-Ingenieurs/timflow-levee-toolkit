"""Sphinx configuration.

The documentation is built from the repository root, with this folder as configuration folder, so
that the README and the notebooks are used where they are:

    python docs/execute_notebooks.py                     # optional: run the notebooks first
    python -m sphinx -b html -c docs . docs/_build/html

The notebooks are not executed by Sphinx: on Read the Docs `docs/execute_notebooks.py` runs them
first (see `.readthedocs.yaml`).
"""

import timflow_levee_toolkit

project = "timflow-levee-toolkit"
author = "CWG Ingenieurs"
copyright = "CWG Ingenieurs"
release = timflow_levee_toolkit.__version__
version = release

extensions = ["myst_nb"]

root_doc = "docs/index"
include_patterns = [
    "docs/index.md",
    "README.md",
    "notebooks/README.md",
    "notebooks/*.ipynb",
    "examples/papendrecht/README.md",
]
exclude_patterns = ["docs/_build", "**/.ipynb_checkpoints"]

nb_execution_mode = "off"
myst_heading_anchors = 3

html_theme = "furo"
# The start page is docs/index.html: index.html in the root of the site redirects to it
html_extra_path = ["_extra"]
# Wide tables in notebook outputs get a horizontal scrollbar
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_title = f"timflow-levee-toolkit {release}"
