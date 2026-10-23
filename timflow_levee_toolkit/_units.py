"""Units of the axis labels, shared by the plot functions of the package.
"""




# Default units for axis labels of the plot functions in this module that take
# a `units` dict. Pass e.g. {"head": "m NAP", "head_rel": "m", "time": "days",
# "x": "m"} to set the vertical datum of the project. ("head": absolute heads,
# "head_rel": heads relative to an average, e.g. fluctuations.)
DEFAULT_UNITS = {"head": "m+ref", "head_rel": "m", "time": "days", "x": "m"}


def _label(name, units, key):
    """Axis label 'name [unit]', with the unit from `units` or `DEFAULT_UNITS`."""
    unit = {**DEFAULT_UNITS, **(units or {})}[key]
    return f"{name} [{unit}]"
