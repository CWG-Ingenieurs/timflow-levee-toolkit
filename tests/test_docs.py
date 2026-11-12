import importlib.util
from pathlib import Path

import nbformat

SCRIPT = Path(__file__).parents[1] / "docs" / "execute_notebooks.py"
spec = importlib.util.spec_from_file_location("execute_notebooks", SCRIPT)
execute_notebooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(execute_notebooks)


def stream(text, name="stdout"):
    return nbformat.v4.new_output("stream", name=name, text=text)


def test_strip_progress_dots_flushed_one_by_one():
    # The calibration prints one dot per model run, each flushed: one output per dot
    cell = nbformat.v4.new_code_cell("cal.fit()")
    cell.outputs = [stream(".") for _ in range(20)] + [stream("\nFit succeeded.\n")]
    nb = nbformat.v4.new_notebook(cells=[cell])
    execute_notebooks.strip_progress(nb)
    assert [o["text"] for o in nb.cells[0].outputs] == ["Fit succeeded.\n"]


def test_strip_progress_keeps_other_output():
    cell = nbformat.v4.new_code_cell("print(...)")
    cell.outputs = [
        stream("a\n"),
        stream("warning\n", name="stderr"),
        nbformat.v4.new_output("execute_result", data={"text/plain": "1"}, execution_count=1),
        stream(" 50%|█████     | 2/4 [00:08<00:08,  4.31s/it]\r"),
        stream("b\n"),
    ]
    nb = nbformat.v4.new_notebook(cells=[cell])
    execute_notebooks.strip_progress(nb)
    outputs = nb.cells[0].outputs
    assert [o.get("text") for o in outputs] == ["a\n", "warning\n", None, "b\n"]
