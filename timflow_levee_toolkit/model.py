"""Timflow cross-section models of a levee.

Plots of the model layout and results, the geohydrological scheme (model
parameters in Excel), observation locations, heads over time and along the
cross-section, and storm events (river level scenarios).

Some functions are standalone copies of functionality proposed but not yet
merged upstream into timflow (see each function's docstring, e.g.
`plot_transient_results` mirrors timflow PR #191). They follow timflow's API
and docstring conventions, so they can be dropped in favor of the upstream
version once it is merged.
"""

from datetime import datetime as dt
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment

from timflow.calibrate import Calibrate

from ._units import _label


# Standalone copy of the method proposed in timflow PR #191
# (https://github.com/timflow-org/timflow/pull/191), not yet merged upstream.
# Docstring below is written as it would read as a `Calibrate` method, so it
# can be copied in near-verbatim if/when that PR lands. Differences from
# that proposed method:
#   - Takes `cal: Calibrate` as an explicit first argument instead of `self`,
#     since a plain function has no implicit bound instance.
#   - NSE is computed via `cal._nse(...)`, reusing the existing @staticmethod
#     already on `Calibrate` in the base `dev` branch (not part of the open
#     PR), rather than duplicating that formula here.
def plot_transient_results(
    cal: Calibrate,
    tmin: float | None = None,
    tmax: float | None = None,
    figsize: tuple[float, float] = (10, 8),
    obs_kwargs: dict | None = None,
    model_kwargs: dict | None = None,
    sharey: bool = False,
    units: dict | None = None,
) -> tuple[plt.Figure, np.ndarray]:
    """Plot modeled vs observed transient head time series.

    Creates one subplot per transient observation with a shared x-axis,
    comparing observed heads to the current model response. Call this
    method before calibration to inspect the initial fit, or after
    calibration to inspect the calibrated fit.

    For a cross-section model (`ModelXsection`), subplots are ordered by
    `(x, layer)` and titled with the observation's location and layer. For
    other model types, where `x` alone is not a meaningful ordering,
    subplots are ordered and titled by observation name instead.

    Parameters
    ----------
    tmin : float, optional
        Start of the plotted time window. Defaults to the earliest
        observation time across all series.
    tmax : float, optional
        End of the plotted time window. Defaults to the latest
        observation time across all series.
    figsize : tuple of float, optional
        Figure size `(width, height)` in inches. Default is `(10, 8)`.
    obs_kwargs : dict, optional
        Keyword arguments passed to `matplotlib.axes.Axes.plot` for
        the observed data. Default: black dots.
    model_kwargs : dict, optional
        Keyword arguments passed to `matplotlib.axes.Axes.plot` for
        the modeled response. Default: blue solid line.
    sharey : bool, optional
        If `True`, all subplots share the same y-axis limits.
        Default is `False`.
    units : dict, optional
        Optional units to append to the axis labels and, for
        cross-section models, the per-subplot `x` value in the title,
        e.g. `{"head": "m", "time": "days", "x": "m"}`.

    Returns
    -------
    fig : matplotlib.figure.Figure
    axes : np.ndarray of matplotlib.axes.Axes
        One Axes per transient observation.
    """
    # Collect transient observations in insertion order
    transient_items = [
        (name, obs)
        for name, obs in cal.observations_dict.items()
        if obs.model_key == "transient"
    ]
    transient_well_items = [
        (name, obs)
        for name, obs in cal.observations_in_well_dict.items()
        if obs.model_key == "transient"
    ]
    all_items = transient_items + transient_well_items
    n_obs = len(all_items)

    if n_obs == 0:
        raise ValueError("No transient observations to plot.")

    # Cross-section models have a meaningful x-coordinate to sort/title
    # on; for other model types (e.g. areal models) fall back to the
    # observation name instead.
    _model_for_type = (
        cal.transient_model if cal.transient_model is not None else cal.steady_model
    )
    is_xsection = type(_model_for_type).__name__ == "ModelXsection"
    if is_xsection:
        all_items = sorted(all_items, key=lambda item: (item[1].x, item[1].layer))
    else:
        all_items = sorted(all_items, key=lambda item: item[0])

    units = units or {}
    head_unit = f" [{units['head']}]" if "head" in units else ""
    time_unit = f" [{units['time']}]" if "time" in units else ""
    x_unit = f" {units['x']}" if "x" in units else ""

    # Default styling
    obs_kw: dict = {"color": "k", "marker": ".", "linestyle": "none"}
    obs_kw.update(obs_kwargs or {})

    model_kw: dict = {"color": "tab:blue", "label": "model"}
    model_kw.update(model_kwargs or {})

    _tr_has_steady = getattr(cal.transient_model, "steady", None) is not None

    # Solve the current model state, just in case, but should already be done usually.
    if cal.steady_model is not None:
        cal.steady_model.solve(silent=True)
    if cal.transient_model is not None:
        cal.transient_model.solve(silent=True)

    # Create subplots
    fig, ax_array = plt.subplots(
        n_obs, 1, sharex=True, sharey=sharey, figsize=figsize, layout="constrained"
    )
    axes = np.atleast_1d(ax_array)

    i = 0
    for ax, (name, obs) in zip(axes, all_items, strict=True):
        dt = obs._time_shift if obs.time_shift is not None else 0.0
        t_plot = obs.t - dt  # shared time axis for observed and modeled

        # Build observed label, annotating any corrections
        obs_label_parts = []
        if obs.time_shift is not None:
            obs_label_parts.append(f"Δt={float(obs._time_shift[0]):.2f}")
        if obs.constant is not None:
            obs_label_parts.append(f"Δh={float(obs._constant[0]):.2f}")
        obs_suffix = f" ({', '.join(obs_label_parts)})" if obs_label_parts else ""
        obs_label = f"{name}{obs_suffix}"

        # Compute observed heads with corrections applied
        if cal.reference_time is not None:
            tref_idx = np.abs(obs.t - cal.reference_time).argmin()
            h_obs_plot = obs.h - obs.h[tref_idx]
        else:
            c = float(obs._constant[0]) if obs.constant is not None else 0.0
            h_obs_plot = obs.h - c

        # Compute modeled heads
        if name in dict(transient_items):
            if obs.normalized or _tr_has_steady:
                hsteady = 0.0
            elif cal.steady_model is not None:
                hsteady = float(
                    np.squeeze(cal.steady_model.head(obs.x, obs.y, layers=obs.layer))
                )
            else:
                hsteady = 0.0
            h_mod = (
                cal.transient_model.head(obs.x, obs.y, obs.t - dt, layers=obs.layer)
                + hsteady
            ).squeeze()
        else:
            h_mod = obs.element.headinside(obs.t - dt)[0]

        if cal.reference_time is not None:
            h_mod = h_mod - h_mod[tref_idx]

        # Apply tmin/tmax window
        mask = np.ones(len(t_plot), dtype=bool)
        if tmin is not None:
            mask &= t_plot >= tmin
        if tmax is not None:
            mask &= t_plot <= tmax

        nse = cal._nse(h_obs_plot[mask], h_mod[mask])
        nse_str = f"NSE={nse:.2f}" if np.isfinite(nse) else "NSE=n/a"
        model_label = f"{model_kw.get('label', 'model')} ({nse_str})"

        model_kw["color"] = f"C{i}"  # cycle through colors for each subplot
        ax.plot(t_plot[mask], h_obs_plot[mask], label=obs_label, **obs_kw)
        ax.plot(t_plot[mask], h_mod[mask], **{**model_kw, "label": model_label})

        if is_xsection:
            ax.set_title(
                f"x: {obs.x:.1f}{x_unit}, layer: {obs.layer}",
                loc="right",
                fontsize="medium",
            )
        else:
            ax.set_title(f"layer: {obs.layer}", loc="right", fontsize="medium")
        ax.set_ylabel(f"head{head_unit}")
        ax.grid(True)
        ax.legend(loc=(0, 1), frameon=False, ncol=2)
        ax.set_xlim(left=t_plot[mask][0], right=t_plot[mask][-1])
        i += 1
    axes[-1].set_xlabel(f"time{time_unit}")
    fig.align_ylabels(axes)
    return fig, axes


# Proposed spatial counterpart to `plot_transient_results` above - not yet
# filed as a timflow issue/PR, written here first to settle on a design.
# Mirrors `plot_transient_results` as closely as the different axis allows:
# same `cal`-first signature, docstring/comment style, `units` convention,
# and reuse of `cal._nse`. Key differences:
#   - Subplots are organized per layer (not per observation), since several
#     observations at different x can share one layer's panel - the spatial
#     equivalent of "one subplot per observation" would put multiple panels
#     out of context with each other.
#   - There is no separate steady-observation bookkeeping: the "observed"
#     value plotted per piezometer is the time-average of its existing
#     transient series (`obs.h.mean()`, optionally windowed by `tmin`/
#     `tmax`), so nothing needs to be registered via `add_steady_head`
#     beyond the transient observations already added for
#     `plot_transient_results`.
# Only meaningful for a cross-section model (plotting head "along x" assumes
# a 1D spatial axis), so unlike `plot_transient_results` there is no
# non-cross-section fallback mode here.
def plot_steady_results(
    cal: Calibrate,
    x1: float,
    x2: float,
    y: float = 0.0,
    npoints: int = 100,
    layers: int | list[int] | None = None,
    tmin: float | None = None,
    tmax: float | None = None,
    figsize: tuple[float, float] = (10, 8),
    obs_kwargs: dict | None = None,
    model_kwargs: dict | None = None,
    sharey: bool = False,
    units: dict | None = None,
) -> tuple[plt.Figure, np.ndarray]:
    """Plot modeled vs observed steady heads along a cross-section.

    Creates one subplot per layer, plotting the steady head profile between
    `x1` and `x2` and overlaying, for each transient observation in that
    layer, the time-average of its observed series.

    Parameters
    ----------
    x1, x2 : float
        Start and end x-coordinates of the line along which the steady head
        profile is evaluated and plotted.
    y : float, optional
        y-coordinate of the cross-section line. Default is `0.0`.
    npoints : int, optional
        Number of points along the line. Default is `100`.
    layers : int or list of int, optional
        Layers to plot. Defaults to all layers that have at least one
        transient observation.
    tmin : float, optional
        Start of the time window averaged per observation. Defaults to
        the earliest observation time in each series.
    tmax : float, optional
        End of the time window averaged per observation. Defaults to
        the latest observation time in each series.
    figsize : tuple of float, optional
        Figure size `(width, height)` in inches. Default is `(10, 8)`.
    obs_kwargs : dict, optional
        Keyword arguments passed to `matplotlib.axes.Axes.scatter` for
        the observed data. Default: black dots.
    model_kwargs : dict, optional
        Keyword arguments passed to `matplotlib.axes.Axes.plot` for
        the modeled response. Default: blue solid line.
    sharey : bool, optional
        If `True`, all subplots share the same y-axis limits.
        Default is `False`.
    units : dict, optional
        Optional units to append to the axis labels, e.g.
        `{"head": "m", "x": "m"}`.

    Returns
    -------
    fig : matplotlib.figure.Figure
    axes : np.ndarray of matplotlib.axes.Axes
        One Axes per layer.
    """
    if cal.steady_model is None:
        raise ValueError("cal.steady_model must be set to plot steady results.")

    # Collect transient observations in insertion order - their time-average
    # stands in for a steady observation, no add_steady_head(...) needed.
    transient_items = [
        (name, obs)
        for name, obs in cal.observations_dict.items()
        if obs.model_key == "transient"
    ]
    transient_well_items = [
        (name, obs)
        for name, obs in cal.observations_in_well_dict.items()
        if obs.model_key == "transient"
    ]
    all_items = transient_items + transient_well_items

    if not all_items:
        raise ValueError("No transient observations to average into steady heads.")

    if layers is None:
        plotlayers = sorted({obs.layer for _, obs in all_items})
    else:
        plotlayers = list(np.atleast_1d(layers))

    units = units or {}
    head_unit = f" [{units['head']}]" if "head" in units else ""
    x_unit = f" [{units['x']}]" if "x" in units else ""

    # Default styling
    obs_kw: dict = {"color": "red", "marker": "_"}
    obs_kw.update(obs_kwargs or {})

    model_kw: dict = {"color": "tab:blue", "label": "model"}
    model_kw.update(model_kwargs or {})

    # Solve the current model state, just in case, but should already be done usually.
    cal.steady_model.solve(silent=True)

    x = np.linspace(x1, x2, npoints)
    y_arr = np.full_like(x, y)

    def _mean_h(obs) -> float:
        mask = np.ones(len(obs.t), dtype=bool)
        if tmin is not None:
            mask &= obs.t >= tmin
        if tmax is not None:
            mask &= obs.t <= tmax
        return float(np.mean(obs.h[mask]))

    fig, ax_array = plt.subplots(
        len(plotlayers), 1, sharex=True, sharey=sharey, figsize=figsize, layout="constrained"
    )
    axes = np.atleast_1d(ax_array)

    for i, (ax, layer) in enumerate(zip(axes, plotlayers, strict=True)):
        h_mod_line = cal.steady_model.headalongline(x, y_arr, layers=[layer])[0]
        model_kw["color"] = f"C{i}"  # cycle through colors for each subplot
        ax.plot(x, h_mod_line, **model_kw)

        layer_items = [(name, obs) for name, obs in all_items if obs.layer == layer]
        h_obs = np.array([_mean_h(obs) for _, obs in layer_items])
        h_mod_at_obs = np.array(
            [
                float(np.squeeze(cal.steady_model.head(obs.x, obs.y, layers=obs.layer)))
                for _, obs in layer_items
            ]
        )
        rmse = float(np.sqrt(np.mean((h_obs - h_mod_at_obs) ** 2)))
        rmse_str = f"RMSE={rmse:.2f}"

        ax.scatter(
            [obs.x for _, obs in layer_items], h_obs, label=f"observed, mean ({rmse_str})", **obs_kw
        )
        for (name, obs), h in zip(layer_items, h_obs, strict=True):
            ax.annotate(name, (obs.x, h), ha="left", va="bottom", fontsize=7)

        ax.set_title(f"layer: {layer}", loc="right", fontsize="medium")
        ax.set_ylabel(f"head{head_unit}")
        ax.grid(True)
        ax.legend(loc=(0, 1), frameon=False, ncol=2)
        ax.set_xlim(x1, x2)
    axes[-1].set_xlabel(f"x{x_unit}")
    fig.align_ylabels(axes)
    return fig, axes



def plot_calibration_locations(ax: plt.Axes, model_transient, calibrate: Calibrate) -> None:
    """Draw calibration piezometer locations on a cross-section axes.

    Piezometers sharing an x-location are fanned out (small horizontal
    offset, larger vertical label offset) ordered shallowest-to-deepest
    left-to-right, so overlapping screens/labels stay legible.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axes to draw on, typically a cross-section axes already created by
        `plot_xsection` or `model.plots.xsection(...)`.
    model_transient : timflow.ModelXsection
        Model used to look up each observation's aquifer geometry
        (`aq.find_aquifer_data`, `zaqtop`/`zaqbot`).
    calibrate : timflow.Calibrate
        Calibration object whose `observations_dict` and
        `observations_in_well_dict` provide the `(x, y, layer)` of each
        piezometer to plot.
    """
    all_obs = {**calibrate.observations_dict, **calibrate.observations_in_well_dict}

    x_groups: dict[float, list] = {}
    for key, s in all_obs.items():
        aq = model_transient.aq.find_aquifer_data(s.x, s.y)
        x_groups.setdefault(s.x, []).append((key, s, aq))

    dx = 1.0  # small horizontal offset per piezometer sharing an x-location
    dz = 2.0  # larger vertical offset per piezometer, for label placement

    for x, items in x_groups.items():
        # Order shallowest to deepest (descending screen-top elevation)
        items = sorted(items, key=lambda item: item[2].zaqtop[item[1].layer], reverse=True)
        n = len(items)
        for idx, (key, s, aq) in enumerate(items):
            ztop = aq.z[0]
            zpb_top = aq.zaqtop[s.layer]
            zpb_bot = aq.zaqbot[s.layer]
            rank = n - 1 - idx  # 0 = deepest (sits at the anchor), n-1 = shallowest
            color = f"C{s.layer + 1}"
            x_plot = s.x + idx * dx  # idx=0 (shallowest) -> leftmost, deeper ones step right
            z_label = ztop + 1 + rank * dz

            ax.plot([x_plot, x_plot], [zpb_top, zpb_bot], c=color, ls="dotted")
            ax.plot([x_plot, x_plot], [z_label, zpb_top], c=color, ls="solid", lw=1.0)
            ax.text(x_plot, z_label, key, ha="left", va="bottom", rotation=45, c=color, fontsize=7)


def add_leakage_factors(
    ax: plt.Axes,
    model_transient,
    model_steady,
    xlim: tuple[float | None, float | None] = (None, None),
) -> None:
    """Label each inhomogeneity with its dominant leakage factor.

    Only a steady model's `aq.lab` is a scalar per layer (dominant
    eigenvalue at `lab[0]`); on a transient model `aq.lab` is
    `(naq, npval)`, one value per Laplace-parameter sample, not a leakage
    factor - see https://github.com/timflow-org/timflow/issues/187. So this
    always reads from `model_steady`, matched to `model_transient`'s
    inhomogeneities by name; an inhomogeneity missing from
    `model_steady.aq.inhomdict` is silently skipped.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axes to draw on, typically a cross-section axes already created by
        `plot_xsection` or `model.plots.xsection(...)`.
    model_transient : timflow.ModelXsection
        Model whose inhomogeneities (name, x-extent, deepest-layer bottom)
        are labelled.
    model_steady : timflow.steady.ModelXsection
        Steady counterpart supplying each inhomogeneity's `lab[0]`.
    xlim : tuple, optional
        If given, clamps each label's x-position to stay within view for
        inhomogeneities extending beyond the plotted range (e.g. to
        +/-inf). A `None` bound leaves that side unclamped. Default is
        `(None, None)`.
    """
    for inhom in model_transient.aq.inhomdict.values():
        if inhom.name not in model_steady.aq.inhomdict:
            continue
        leakagefactor = model_steady.aq.inhomdict[inhom.name].lab[0]
        x_left = inhom.x1 if xlim[0] is None else max(inhom.x1, xlim[0])
        x_right = inhom.x2 if xlim[1] is None else min(inhom.x2, xlim[1])
        ax.text(
            (x_left + x_right) / 2,
            inhom.zaqbot[-1],
            f"λ = {leakagefactor:.0f} m",
            horizontalalignment="center",
            color="red",
            bbox=dict(facecolor="darkgrey", alpha=0.8),
        )


def add_diffusivity_summary(
    ax: plt.Axes,
    model_transient,
    model_steady=None,
    diffusivity_inhom: str | None = "hinterland",
    ratio_inhoms: tuple[str, str] | None = ("river", "hinterland"),
) -> None:
    """Add a summary text box with aquifer diffusivity and a leakage-ratio.

    Diffusivity (deepest layer) is read from `model_transient` - `aq.D` is
    unaffected by the transient/steady `lab` shape difference noted in
    `add_leakage_factors`. The leakage-factor ratio needs `model_steady`
    for the same reason `add_leakage_factors` does. Either part, or the
    whole box, is skipped (not a `KeyError`) when the configured
    inhomogeneity name(s) aren't present.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axes to draw on.
    model_transient : timflow.ModelXsection
        Supplies the diffusivity half of the summary.
    model_steady : timflow.steady.ModelXsection, optional
        Supplies the leakage-ratio half. Default is `None` (ratio skipped).
    diffusivity_inhom : str, optional
        Name of the inhomogeneity whose deepest-layer diffusivity is shown.
        Skipped if `None` or not present in `model_transient.aq.inhomdict`.
        Default is `"hinterland"`.
    ratio_inhoms : tuple of str, optional
        Names of the two inhomogeneities whose leakage-factor ratio is
        shown. Skipped if `None`, `model_steady` is `None`, or either name
        is not present in `model_steady.aq.inhomdict`. Default is
        `("river", "hinterland")`.
    """
    summary_lines = []
    if diffusivity_inhom is not None and diffusivity_inhom in model_transient.aq.inhomdict:
        diffusivity = model_transient.aq.inhomdict[diffusivity_inhom].D[-1]
        summary_lines.append(f"diffusivity ({diffusivity_inhom}) = {diffusivity:.1e} m$^2$/d")
    if (
        model_steady is not None
        and ratio_inhoms is not None
        and all(name in model_steady.aq.inhomdict for name in ratio_inhoms)
    ):
        name_a, name_b = ratio_inhoms
        lambda_a = model_steady.aq.inhomdict[name_a].lab[0]
        lambda_b = model_steady.aq.inhomdict[name_b].lab[0]
        summary_lines.append(f"λ{name_a} / λ{name_b} = {lambda_a / lambda_b:.4f}")

    if summary_lines:
        ax.text(
            0.02,
            0.98,
            "\n".join(summary_lines),
            transform=ax.transAxes,
            horizontalalignment="left",
            verticalalignment="top",
            color="navy",
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="navy"),
        )


def add_element_labels(ax: plt.Axes, model_transient) -> None:
    """Label each element in `model_transient.elementdict` at its location.

    Not covered by the native `model.plots.xsection(...)`'s `names=`/
    `labels=` options, which label inhomogeneities and layers, not
    individual elements (e.g. a no-flow wall).

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        Axes to draw on.
    model_transient : timflow.ModelXsection
        Model whose `elementdict` is labelled.
    """
    for element in model_transient.elementdict.values():
        ax.text(
            element.xld,
            element.aq.zaqbot[-1],
            element.label,
            rotation=90,
            ha="right",
            va="bottom",
            fontsize=8,
        )


def plot_xsection(
    model_transient,
    model_steady=None,
    calibrate: Calibrate | None = None,
    xlim: tuple[float | None, float | None] = (None, None),
    zlim: tuple[float | None, float | None] = (None, None),
    figsize: tuple[float, float] = (10, 5),
    labels: bool = False,
    params: bool = True,
    names: bool = True,
    fmt: str = ".2f",
    units: dict | None = None,
    axis_units: dict | None = None,
    diffusivity_inhom: str | None = "hinterland",
    ratio_inhoms: tuple[str, str] | None = ("river", "hinterland"),
    **kwargs,
) -> tuple[plt.Figure, plt.Axes]:
    """Plot the cross-section of the model, with leakage-factor annotations.

    Thin composer: creates the figure, delegates the inhomogeneity/
    parameter/name drawing to timflow's own `model.plots.xsection(...)`
    (forwarding `**kwargs` to it, so any native option - `horizontal_axis`,
    `boundaries`, `hstar`, `layer_names`, ... - is still reachable), then
    calls `add_leakage_factors`, `add_diffusivity_summary`,
    `add_element_labels` and `plot_calibration_locations` in sequence. Each
    of those is a standalone function and can be called directly instead,
    on a figure/axes built however you like.

    Parameters
    ----------
    model_transient : timflow.ModelXsection
        The timflow model to plot.
    model_steady : timflow.steady.ModelXsection, optional
        Steady counterpart of `model_transient`, passed through to
        `add_leakage_factors`/`add_diffusivity_summary`. Leakage factors
        are only shown when this is given - see `add_leakage_factors` for
        why. Default is `None`.
    calibrate : timflow.Calibrate, optional
        Calibration object with observation locations to overlay.
        Default is `None`.
    xlim, zlim : tuple, optional
        Axis limits. Default is `(None, None)` for both.
    figsize : tuple, optional
        Figure size. Default is `(10, 5)`.
    labels : bool, optional
        Whether to display layer-numbering labels. Default is `False`.
    params : bool, optional
        Whether to display parameter values, leakage factors, and the
        diffusivity/leakage-ratio summary box. Default is `True`.
    names : bool, optional
        Whether to display inhomogeneity names. Default is `True`.
    fmt : str, optional
        Format string for parameter values, e.g. `".2f"`. Default is
        `".2f"`.
    units : dict, optional
        Units keyed by timflow parameter name, passed to the native
        `xsection` plotter. Defaults to
        `{"kaq": "m/d", "Saq": "m$^{-1}$", "Sll": "m$^{-1}$", "c": "d"}`.
    axis_units : dict, optional
        Units for the axis labels (keys 'x' and 'head', see `DEFAULT_UNITS`),
        e.g. `{"head": "m NAP", "x": "m"}` gives the z-axis label
        'z [m NAP]'. Default: 'x [m]' and 'z [m + ref]'.
    diffusivity_inhom : str, optional
        See `add_diffusivity_summary`. Default is `"hinterland"`.
    ratio_inhoms : tuple of str, optional
        See `add_diffusivity_summary`. Default is `("river", "hinterland")`.
    **kwargs
        Forwarded to `model_transient.plots.xsection(...)`.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    """
    if units is None:
        units = {"kaq": "m/d", "Saq": "m$^{-1}$", "Sll": "m$^{-1}$", "c": "d"}

    f, ax = plt.subplots(1, 1, figsize=figsize)

    # Inhomogeneities, elements and Hstar values - timflow's own plotter
    model_transient.plots.xsection(
        xy=[(xlim[0], None), (xlim[1], None)],
        params=params,
        labels=labels,
        names=names,
        ax=ax,
        fmt=fmt,
        sep="\n",
        units=units,
        **kwargs,
    )

    if params and model_steady is not None:
        add_leakage_factors(ax, model_transient, model_steady, xlim=xlim)

    if params:
        add_diffusivity_summary(
            ax,
            model_transient,
            model_steady=model_steady,
            diffusivity_inhom=diffusivity_inhom,
            ratio_inhoms=ratio_inhoms,
        )

    add_element_labels(ax, model_transient)

    if calibrate is not None:
        plot_calibration_locations(ax, model_transient, calibrate)

    ax.set_xlim(*xlim)
    ax.set_ylim(*zlim)
    ax.set_xlabel(_label("x", axis_units, "x"))
    ax.set_ylabel(_label("z", axis_units, "head") if axis_units else "z [m + ref]")
    return f, ax


def read_model_params(excel_path, tab_name="initial"):
    """Read model parameters per inhomogeneity from the parameters Excel file.

    Counterpart of `write_model_params`: a tab written by that function can
    be read back with this one. The tab has one row per inhomogeneity and
    layer, with columns 'inhomogeneity_id', 'layer', 'semiconf_top',
    'aquifer_top', 'aquifer_bottom', 'aquifer_k', 'aquitard_c',
    'aquifer_s', 'aquitard_s' and optionally 'leffaq' and 'leffll'.

    Parameters
    ----------
    excel_path : Path or str
        Path to the Excel parameters file.
    tab_name : str, optional
        Name of the sheet to read. Default is 'initial'.

    Returns
    -------
    inhom_params : dict
        Per inhomogeneity name a dict with the timflow arguments:
          z      : [semiconf_top, aq0_top, aq0_bot, aq1_top, aq1_bot, ...]
          kaq    : aquifer hydraulic conductivity per layer [m/day]
          c      : hydraulic resistance of the aquitards per layer [days]
          Saq    : elastic aquifer storage per layer [1/m]
          Sll    : elastic aquitard storage per layer [1/m]
          leffaq : aquifer loading efficiency per layer [-] (0 if missing)
          leffll : aquitard loading efficiency per layer [-] (0 if missing)
    naq : int
        Number of aquifer layers (assumed equal for all inhomogeneities).
    """
    mp = pd.read_excel(excel_path, sheet_name=tab_name)
    naq = int(mp["layer"].max()) + 1

    inhom_params = {}
    for name, rows in mp.groupby("inhomogeneity_id", sort=False):
        rows = rows.sort_values("layer")
        z = [float(rows["semiconf_top"].iloc[0])]  # top of semi-confining layer
        for top, bottom in zip(rows["aquifer_top"], rows["aquifer_bottom"]):
            z += [top, bottom]

        # Loading efficiency: default to 0 if the column is missing or cells are empty
        leff = {
            col: rows[col].fillna(0).tolist() if col in rows.columns else [0] * len(rows)
            for col in ("leffaq", "leffll")
        }
        inhom_params[name] = {
            "z": z,
            "kaq": rows["aquifer_k"].tolist(),
            "c": rows["aquitard_c"].tolist(),
            "Saq": rows["aquifer_s"].tolist(),
            "Sll": rows["aquitard_s"].tolist(),
            **leff,
        }
    return inhom_params, naq


def print_model_params(inhom_params):
    """Print the parameters per inhomogeneity, e.g. to check `read_model_params`.

    Parameters
    ----------
    inhom_params : dict
        Parameters per inhomogeneity as returned by `read_model_params`.
    """
    naq = len(next(iter(inhom_params.values()))["kaq"])
    print(f"Number of aquifer layers: {naq}")
    for name, params in inhom_params.items():
        print(f"--- {name} ---")
        for key, value in params.items():
            print(f"  {key:<6} = {value}")


def _unique_tab_name(tab_name, existing):
    """Return `tab_name`, or `tab_name` + timestamp if that tab already exists.

    Excel compares tab names case-insensitively and allows at most 31
    characters, so the base name is shortened if needed to fit the
    timestamp (format `%Y%m%d_%H%M%S`, as in `finalize_and_save`). If that
    name exists as well (two writes within one second), a sequence number
    is added.
    """
    existing = {name.lower() for name in existing}
    if tab_name.lower() not in existing:
        return tab_name
    timestamp = f"_{dt.now():%Y%m%d_%H%M%S}"
    suffix, n = timestamp, 1
    while (unique := tab_name[: 31 - len(suffix)] + suffix).lower() in existing:
        n += 1
        suffix = f"{timestamp}_{n}"
    print(f"Tab '{tab_name}' already exists; using '{unique}' instead.")
    return unique


def write_model_params(ml, excel_path, tab_name='calibrated'):
    """Write current model parameters to a new tab in the parameters Excel file.

    Counterpart of `read_model_params`: the written tab can be read back
    with that function, e.g. to start a new run from calibrated values.

    Builds a fresh DataFrame from the current model state -- no template needed.
    Geometry (z-array), kaq, c, Saq and Sll are all read from ml.aq.inhomdict.
    Columns not present in the model (semiconf_head, npor, rate) are left NaN.

    Number formatting applied in Excel:
      - aquifer_k, aquitard_c : 2 decimal places  (0.00)
      - aquifer_s, aquitard_s : scientific notation, 2 digits  (0.00E+00)

    Parameters
    ----------
    ml : timflow ModelXsection
        The model, typically after calibration.
    excel_path : Path or str
        Path to the Excel parameters file.
    tab_name : str
        Name of the sheet to write (default: 'calibrated'). If a tab with
        this name already exists, a timestamp is appended (e.g.
        'calibrated_20261021_160428') so existing results are never
        overwritten. The tab name that was used is printed and stored in
        `result.attrs["tab_name"]`.

    Returns
    -------
    pd.DataFrame  The new parameter DataFrame that was written.
    """

    columns = [
        'inhomogeneity_id', 'layer',
        'aquifer_top', 'aquifer_bottom', 'aquitard_c', 'aquifer_k',
        'semiconf_top', 'semiconf_head',
        'aquitard_s', 'aquifer_s',
        'aquitard_npor', 'aquifer_npor', 'rate', 'leffaq', 'leffll',
    ]

    rows = []
    for inhom_name, inhom in ml.aq.inhomdict.items():
        for layer in range(ml.aq.naq):
            rows.append(
                {
                    "inhomogeneity_id": inhom_name,
                    "layer": layer,
                    "aquifer_top": inhom.z[2 * layer + 1],
                    "aquifer_bottom": inhom.z[2 * layer + 2],
                    "aquitard_c": inhom.c[layer],
                    "aquifer_k": inhom.kaq[layer],
                    "semiconf_top": inhom.z[0] if layer == 0 else float("nan"),
                    "aquifer_s": inhom.Saq[layer]
                    if hasattr(inhom.Saq, "__getitem__")
                    else inhom.Saq,
                    "aquitard_s": inhom.Sll[layer]
                    if hasattr(inhom.Sll, "__getitem__")
                    else inhom.Sll,
                    "leffaq": inhom.leffaq[layer],
                    "leffll": inhom.leffll[layer],
                }
            )

    mp_out = pd.DataFrame(rows, columns=columns)
    mp_out['layer'] = mp_out['layer'].astype(int)

    # Never overwrite an existing tab: make the name unique with a timestamp
    excel_path = Path(excel_path)
    book = load_workbook(excel_path)
    tab_name = _unique_tab_name(tab_name, book.sheetnames)
    book.close()

    # Number formats per column
    col_formats = {
        'aquifer_k' : '0.00',
        'aquitard_c': '0.00',
        'aquifer_s' : '0.00E+00',
        'aquitard_s': '0.00E+00',
    }
    center = Alignment(horizontal='center', vertical='center')

    with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a') as writer:
        mp_out.to_excel(writer, sheet_name=tab_name, index=False)
        ws = writer.sheets[tab_name]

        # Column letter lookup (1-based openpyxl index -> letter)
        col_letter = {
            col: ws.cell(row=1, column=idx + 1).column_letter
            for idx, col in enumerate(mp_out.columns)
        }

        # Apply number formats to data rows (skip header row 1)
        for col_name, fmt in col_formats.items():
            letter = col_letter[col_name]
            for row in ws.iter_rows(min_row=2, min_col=ws[letter + '1'].column,
                                    max_col=ws[letter + '1'].column):
                for cell in row:
                    cell.number_format = fmt

        # Center all cells and auto-fit column widths
        for col_cells in ws.columns:
            col_name = col_cells[0].value          # header value
            fmt      = col_formats.get(col_name)

            # Estimate display width per cell
            widths = [len(str(col_cells[0].value) or '')]   # header
            for cell in col_cells[1:]:
                if cell.value is None or (isinstance(cell.value, float) and np.isnan(cell.value)):
                    widths.append(1)
                elif fmt == '0.00E+00':
                    widths.append(10)                    # e.g. '1.00E-04'
                elif fmt == '0.00':
                    widths.append(len(f'{cell.value:.2f}'))
                else:
                    widths.append(len(str(cell.value)))

            ws.column_dimensions[col_cells[0].column_letter].width = max(widths) + 2

            for cell in col_cells:
                cell.alignment = center

    print(f"Parameters written to tab '{tab_name}' in '{excel_path.name}'")
    mp_out.attrs["tab_name"] = tab_name
    return mp_out


# Columns of the model parameter tab, with explanation for the template
PARAMETER_COLUMNS = {
    "inhomogeneity_id": "Name of the zone (inhomogeneity): river, foreland, hinterland",
    "layer": "Aquifer number, 0 = upper aquifer",
    "semiconf_top": "Top of the semi-confining top layer [m NAP] (only in the row of layer 0)",
    "aquifer_top": "Top of the aquifer [m NAP]",
    "aquifer_bottom": "Bottom of the aquifer [m NAP]",
    "aquitard_c": "Resistance of the aquitard ABOVE this aquifer [d] (layer 0: semi-confining top layer)",
    "aquifer_k": "Horizontal hydraulic conductivity of the aquifer [m/d]",
    "aquitard_s": "Specific storage of the aquitard above this aquifer [1/m]",
    "aquifer_s": "Specific storage of the aquifer [1/m]",
    "leffaq": "Loading efficiency of the aquifer [-], 0 to 1 (optional, default 0)",
    "leffll": "Loading efficiency of the aquitard above this aquifer [-], 0 to 1 (optional, default 0)",
}


def create_parameter_template(path, zones=("river", "foreland", "hinterland"), naq=2, tab_name="initial"):
    """Create an empty model parameter Excel file to fill in.

    The file gets a tab `tab_name` with one row per zone and aquifer, in the
    format read by `read_model_params`, and a tab 'explanation' describing
    the columns. An existing file is never overwritten.

    Parameters
    ----------
    path : str or pathlib.Path
        Excel file to create.
    zones : sequence of str, optional
        Zone (inhomogeneity) names. Default is ('river', 'foreland',
        'hinterland'), as used by the model notebook.
    naq : int, optional
        Number of aquifers (the same in every zone). Default is 2.
    tab_name : str, optional
        Name of the parameter tab. Default is 'initial'.

    Returns
    -------
    pathlib.Path
    """
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"'{path}' already exists; not overwritten")
    rows = [{"inhomogeneity_id": zone, "layer": layer} for zone in zones for layer in range(naq)]
    params = pd.DataFrame(rows, columns=list(PARAMETER_COLUMNS))
    explanation = pd.DataFrame(
        {"column": list(PARAMETER_COLUMNS), "explanation": list(PARAMETER_COLUMNS.values())}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        params.to_excel(writer, sheet_name=tab_name, index=False)
        explanation.to_excel(writer, sheet_name="explanation", index=False)
        for sheet in writer.sheets.values():
            for col in sheet.columns:
                sheet.column_dimensions[col[0].column_letter].width = max(
                    len(str(cell.value)) if cell.value is not None else 0 for cell in col
                ) + 2
    return path


def validate_model_params(inhom_params, naq, zones=("river", "foreland", "hinterland")):
    """Check the geohydrological scheme read by `read_model_params`.

    Raises one error listing all problems: missing zones, a different number
    of aquifers per zone, empty values, tops and bottoms that are not in
    descending order, and values out of range.

    Parameters
    ----------
    inhom_params : dict
        From `read_model_params`.
    naq : int
        Number of aquifers, from `read_model_params`.
    zones : sequence of str, optional
        Zones that must be present. Default is ('river', 'foreland',
        'hinterland').

    Returns
    -------
    dict
        `inhom_params`, unchanged, if no problems were found.
    """
    problems = []
    missing = [z for z in zones if z not in inhom_params]
    if missing:
        problems.append(f"missing zones: {missing}")
    for zone, p in inhom_params.items():
        if len(p["kaq"]) != naq:
            problems.append(f"{zone}: {len(p['kaq'])} aquifers instead of {naq} (all zones need the same number)")
            continue
        for key in ("z", "kaq", "c", "Saq", "Sll"):
            if any(pd.isna(v) for v in p[key]):
                problems.append(f"{zone}: empty values in '{key}'")
        z = np.asarray(p["z"], dtype=float)
        if not np.isnan(z).any():
            # [semiconf_top, aq0_top, aq0_bot, aq1_top, aq1_bot, ...]: aquifers must have a
            # positive thickness, aquitards (between them) may have zero thickness
            if np.any(z[1::2] <= z[2::2]):
                problems.append(f"{zone}: aquifer bottom not below aquifer top")
            if np.any(np.diff(z)[::2] > 0):
                problems.append(f"{zone}: aquitard bottom above its top (z must decrease downwards)")
        for key in ("kaq", "c", "Saq", "Sll"):
            if any(v <= 0 for v in p[key] if pd.notna(v)):
                problems.append(f"{zone}: '{key}' must be positive")
        for key in ("leffaq", "leffll"):
            if any(not 0 <= v <= 1 for v in p[key] if pd.notna(v)):
                problems.append(f"{zone}: '{key}' must be between 0 and 1")
    if problems:
        raise ValueError("Problems in the model parameters:\n- " + "\n- ".join(problems))
    return inhom_params


def make_obslocs(piezometers):
    """Create the observation locations table used by the model notebooks.

    Parameters
    ----------
    piezometers : pandas.DataFrame
        Piezometers of one transect (e.g. from `read_piezometers`); must have
        columns 'x_crosssection' and 'modellayer'.

    Returns
    -------
    pandas.DataFrame
        Indexed by piezometer name ('name', or 'locatie' if 'name' is
        missing) with columns 'x_crosssection', 'modellayer' and any of
        the optional columns that are present (e.g. 'use_calibration').
    """
    required = ["x_crosssection", "modellayer"]
    missing = [col for col in required if col not in piezometers.columns]
    if missing:
        raise KeyError(f"Required columns missing in piezometer data: {missing}")

    optional = ["name", "locatie", "peilbuis", "filter_top", "filter_bottom",
                "screen_top", "screen_bottom", "object_id", "omschrijving",
                "series_ID", "use_calibration"]
    cols = required + [col for col in optional if col in piezometers.columns]
    obslocs = pd.DataFrame(piezometers[cols])

    for index_col in ("name", "locatie"):
        if index_col in obslocs.columns:
            return obslocs.set_index(index_col)
    return obslocs


def select_obslocs(df_t, obslocs):
    """Select per observation location the column of its own x and layer.

    Parameters
    ----------
    df_t : pandas.DataFrame
        Time series with MultiIndex columns `(layer, x)`, e.g. from
        `calculate_head_t` for `obslocs["x_crosssection"].unique()`.
    obslocs : pandas.DataFrame
        Observation locations; must have columns 'x_crosssection' and
        'modellayer'.

    Returns
    -------
    pandas.DataFrame
        Same index as `df_t`, with MultiIndex columns `(layer, obsloc)`.
    """
    columns = {
        (int(row["modellayer"]), obsloc): df_t[(int(row["modellayer"]), row["x_crosssection"])]
        for obsloc, row in obslocs.iterrows()
    }
    df = pd.DataFrame(columns, index=df_t.index)
    df.columns.names = ["layer", "obsloc"]
    return df


def to_tsandhstar(series):
    """Convert a head time series to a timflow `tsandhstar` boundary condition.

    timflow keeps `hstar` constant from each time until the next one, so
    each step gets the average of the two measurements that bound it:
    `hstar_i = (h_i + h_(i+1)) / 2` at time `t_i`. NaN values are dropped
    first; the last measurement only closes the last step.

    Parameters
    ----------
    series : pandas.Series
        Heads with the time [days] as index, e.g. `obs_dh[loc_river]`.

    Returns
    -------
    list of tuple
        `[(t0, hstar0), (t1, hstar1), ...]`, one entry less than the number
        of non-NaN values in `series`.
    """
    h = series.dropna()
    hstar = (h + h.shift(-1)) / 2
    return hstar.dropna().to_frame().to_records().tolist()


def calculate_head_t(model_transient, xlocs, t, model_steady=None):
    """Calculate heads over time at several x-locations, for all layers.

    Parameters
    ----------
    model_transient : timflow.transient.ModelXsection
        Solved transient model.
    xlocs : array_like
        x-coordinates [m] at which heads are computed (y=0).
    t : array_like
        Times [days].
    model_steady : timflow.steady.ModelXsection, optional
        If given, its steady head is added to the transient head, so the
        result is the total head (e.g. in m NAP). Default is None: only the
        transient head (the fluctuation).

    Returns
    -------
    pandas.DataFrame
        Indexed by time with MultiIndex columns `(layer, x)`.
    """
    t = np.asarray(t)
    columns = {}
    for x in xlocs:
        h = model_transient.head(x, 0, t)
        if model_steady is not None:
            h = h + model_steady.head(x, 0)[:, np.newaxis]
        for layer in range(h.shape[0]):
            columns[(layer, x)] = h[layer]
    df = pd.DataFrame(columns, index=pd.Index(t, name="time [days]"))
    df.columns.names = ["layer", "x"]
    return df


def plot_head_t(df_t, river=None, markers=None, ylabel=None, figsize=None, units=None, relative=False):
    """Plot time series with one subplot per model layer.

    Parameters
    ----------
    df_t : pandas.DataFrame
        Time series with time [days] as index and MultiIndex columns
        `(layer, label)`, e.g. from `calculate_head_t` (label = x) or
        `select_obslocs` (label = observation location). Numeric labels
        are shown as "x = ... m".
    river : pandas.Series, optional
        River head with time [days] as index, plotted as a red dashed line
        in every subplot.
    markers : pandas.DataFrame, optional
        Markers indexed by label (a label may occur more than once) with two
        columns: time and value (e.g. `df_rf_mhw[["t_mhw_mod", "rf_mhw_mod"]]`).
        Plotted in the color of the line of that label.
    ylabel : str, optional
        Label of the y-axes. Default is 'head [unit]' from `units`.
    figsize : tuple of float, optional
        Figure size. Default is `(10, 3 * nlayers)`.
    units : dict, optional
        Units for the axis labels, see `DEFAULT_UNITS`.
    relative : bool, optional
        True if `df_t` holds heads relative to an average (e.g. the transient
        part only): the label then uses the unit of 'head_rel'. Default is
        False.

    Returns
    -------
    fig : matplotlib.figure.Figure
    axes : numpy.ndarray of matplotlib.axes.Axes
        One axes per layer.
    """
    if ylabel is None:
        ylabel = _label("head", units, "head_rel" if relative else "head")
    layers = sorted(df_t.columns.get_level_values(0).unique())
    figsize = figsize or (10, 3 * len(layers))
    fig, axes = plt.subplots(
        len(layers), 1, figsize=figsize, sharex=True, sharey=True, layout="constrained"
    )
    axes = np.atleast_1d(axes)

    for ax, layer in zip(axes, layers):
        if river is not None:
            ax.plot(river.index, river.values, label="river", color="r", linestyle="--")
        for label, h in df_t[layer].items():
            name = f"x = {label:.1f} m" if isinstance(label, (int, float, np.number)) else str(label)
            (line,) = ax.plot(h.index, h.values, label=name)
            if markers is not None:
                rows = markers[markers.index == label]
                ax.plot(rows.iloc[:, 0], rows.iloc[:, 1], "o", color=line.get_color(), ms=7, zorder=5)
        ax.legend(loc=(0, 1), frameon=False, ncol=5, fontsize="x-small")
        ax.set_ylabel(ylabel)
        ax.set_title(f"layer {layer}", loc="right")
        ax.grid(True)
    axes[-1].set_xlabel(_label("time", units, "time"))
    return fig, axes


def plot_head_x(x, curves, styles=None, cmap=None, ylabel=None, figsize=None, units=None, relative=False):
    """Plot curves along the cross-section with one subplot per model layer.

    Parameters
    ----------
    x : array_like
        x-coordinates [m].
    curves : dict
        Per legend label an array of shape `(nlayers, len(x))`, e.g. a time
        step of `model.headalongline(...)` or the maximum over time.
    styles : dict, optional
        Per legend label a dict of keyword arguments for `Axes.plot`
        (e.g. `{"max": {"color": "k", "linestyle": ":"}}`).
    cmap : str or matplotlib colormap, optional
        Colormap for the curves without a color in `styles`, in the order
        of `curves` (e.g. "Spectral" for successive time steps).
    ylabel : str, optional
        Label of the y-axes. Default is 'head [unit]' from `units`.
    figsize : tuple of float, optional
        Figure size. Default is `(10, 3 * nlayers)`.
    units : dict, optional
        Units for the axis labels, see `DEFAULT_UNITS`.
    relative : bool, optional
        True if the curves are heads relative to an average: the label then
        uses the unit of 'head_rel'. Default is False.

    Returns
    -------
    fig : matplotlib.figure.Figure
    axes : numpy.ndarray of matplotlib.axes.Axes
        One axes per layer.
    """
    x = np.asarray(x)
    styles = styles or {}
    if ylabel is None:
        ylabel = _label("head", units, "head_rel" if relative else "head")
    nlayers = next(iter(curves.values())).shape[0]
    figsize = figsize or (10, 3 * nlayers)
    fig, axes = plt.subplots(
        nlayers, 1, figsize=figsize, sharex=True, sharey=True, layout="constrained"
    )
    axes = np.atleast_1d(axes)

    # Colors from the colormap for curves without an explicit color
    no_color = [label for label in curves if "color" not in styles.get(label, {})]
    colors = {}
    if cmap is not None:
        cmap = plt.get_cmap(cmap)
        colors = {label: cmap(i / len(no_color)) for i, label in enumerate(no_color)}

    for layer, ax in enumerate(axes):
        for label, h in curves.items():
            kwargs = {"color": colors.get(label), **styles.get(label, {})}
            ax.plot(x, h[layer], label=label, **kwargs)
        ax.legend(loc=(0, 1), frameon=False, ncol=8, fontsize="x-small")
        ax.set_ylabel(ylabel)
        ax.set_title(f"layer {layer}", loc="right")
        ax.set_xlim(x.min(), x.max())
        ax.grid(True)
    axes[-1].set_xlabel(_label("x", units, "x"))
    return fig, axes


def read_storm_event(
    fname, h_river_avg, time_col="Tijd (uur)", level_col="Waterstand (m+NAP)", skiprows=9
):
    """Read a storm event river water level time series ('waterstandsverloop') from Excel.

    The Excel file has a number of header rows (`skiprows`), a time column
    [hours] and a water level column (e.g. m NAP).

    Parameters
    ----------
    fname : str or pathlib.Path
        Path to the storm event Excel file.
    h_river_avg : float
        Average river head in the daily situation, in the same datum as the
        water level column (e.g. m NAP), e.g. `obs_ref[loc_river].mean()`.
    time_col : str, optional
        Name of the time column [hours]. Default is 'Tijd (uur)'.
    level_col : str, optional
        Name of the water level column (e.g. [m NAP]). Default is
        'Waterstand (m+NAP)'.
    skiprows : int, optional
        Number of rows above the column header row. Default is 9.

    Returns
    -------
    pandas.DataFrame
        Indexed by 'time' [days], shifted so that the series starts at 0,
        with columns:
          't_original'  : time as given in the file [days]
          'h_river'     : river water level (datum of the file, e.g. m NAP)
          'h_river_rel' : river water level relative to `h_river_avg` [m]
    """
    ws = pd.read_excel(fname, skiprows=skiprows, index_col=time_col)
    t_original = ws.index.to_numpy() / 24.0
    h_river = ws[level_col].to_numpy()

    df = pd.DataFrame(
        {
            "t_original": t_original,
            "h_river": h_river,
            "h_river_rel": h_river - h_river_avg,
        },
        index=pd.Index(t_original - t_original[0], name="time"),
    )
    return df


def plot_storm_event(df_storm_event, figsize=(10, 5), units=None):
    """Plot a river water level time series read with `read_storm_event`.

    Upper graph: the original water level (e.g. m NAP) against the original time.
    Lower graph: the water level relative to the average river head against
    the shifted time (starting at 0), as used for the model boundary.

    The axis limits of both graphs are shifted by the same time and head
    offsets, so the curves line up vertically and the average river head
    (dotted line) is at the same height in both graphs.

    Parameters
    ----------
    df_storm_event : pandas.DataFrame
        Output of `read_storm_event`.
    figsize : tuple of float, optional
        Figure size `(width, height)` in inches. Default is `(10, 5)`.
    units : dict, optional
        Units for the axis labels, see `DEFAULT_UNITS`.

    Returns
    -------
    fig : matplotlib.figure.Figure
    axes : numpy.ndarray of matplotlib.axes.Axes
        `[upper, lower]`.
    """
    t_original = df_storm_event["t_original"]
    h_river = df_storm_event["h_river"]

    # Offsets between the two graphs (constant by construction in read_storm_event)
    dt = t_original.iloc[0] - df_storm_event.index[0]
    h_river_avg = (h_river - df_storm_event["h_river_rel"]).iloc[0]

    # Common limits in the coordinates of the upper graph; include the
    # average river head so its line is visible in both graphs
    xlim = (t_original.min(), t_original.max())
    ymin, ymax = min(h_river.min(), h_river_avg), max(h_river.max(), h_river_avg)
    pad = 0.05 * (ymax - ymin)
    ylim = (ymin - pad, ymax + pad)

    fig, axes = plt.subplots(2, 1, figsize=figsize, layout="constrained")

    ax = axes[0]
    ax.plot(t_original, h_river, color="C0")
    ax.axhline(h_river_avg, color="k", linestyle=":", linewidth=1)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_title("Waterstandsverloop - original", loc="right")
    ax.set_xlabel(_label("time", units, "time"))
    ax.set_ylabel(_label("head", units, "head"))
    ax.grid(True)

    ax = axes[1]
    ax.plot(df_storm_event.index, df_storm_event["h_river_rel"], color="C1")
    ax.axhline(0, color="k", linestyle=":", linewidth=1, label="average river head")
    ax.set_xlim(xlim[0] - dt, xlim[1] - dt)
    ax.set_ylim(ylim[0] - h_river_avg, ylim[1] - h_river_avg)
    ax.set_title("Storm event relative to average river head, time shifted to 0", loc="right")
    ax.set_xlabel(_label("time since start", units, "time"))
    ax.set_ylabel(_label("head", units, "head_rel"))
    ax.legend(loc=(0, 1), frameon=False, fontsize="x-small")
    ax.grid(True)
    fig.suptitle("Illustration how the storm event is modified", fontweight="bold")

    return fig, axes
