"""Every figure in the app. Functions take tables and return Plotly figures."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import theme as th
from .analysis import ACCEPTED, is_edge, samples
from .reader import COLS, ROWS, Plate

#: Keeps a selection from dimming the points it did not pick.
_KEEP = dict(selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)))


def hover_text(d: pd.DataFrame) -> pd.Series:
    """One tooltip per well, carrying identity and the full fit diagnostics."""
    if d.empty:
        return pd.Series([], dtype=object)
    r2 = d.r2.map(lambda v: f"{v:.4f}" if np.isfinite(v) else "undefined (flat)")
    norm = d.vmax_norm.map(lambda v: f"{v:.3f}" if np.isfinite(v) else "–")
    return ("<b>" + d.label + "</b>  " + d.role + "<br>"
            + "V<sub>max</sub>  " + d.vmax.map("{:+.4f}".format) + " ΔA340/min<br>"
            + "norm  " + norm + " × plate +ctrl<br>"
            + "R²  " + r2 + "<br>"
            + "window  " + d.n_points.astype(str) + " pts to "
            + d.t_end_s.map(lambda v: f"{v:.0f}" if np.isfinite(v) else "–") + " s<br>"
            + "status  " + d.status + " (" + d.stopped_by + ")")


def _legend_key(fig: go.Figure, colours: dict[str, str], hatched: list[str]) -> None:
    """Legend-only entries: the bars themselves carry per-bar colour and hatching."""
    for name, c in colours.items():
        fig.add_trace(go.Bar(x=[None], y=[None], name=name, marker_color=c,
                             hoverinfo="skip"))
    for role in hatched:
        fig.add_trace(go.Bar(x=[None], y=[None], name=th.ROLE_LAB[role], hoverinfo="skip",
                             marker=dict(color="#FFFFFF", line=dict(color=th.INK2, width=1),
                                         pattern=dict(shape=th.CONTROL_PATTERN[role],
                                                      fgcolor=th.INK2, size=5))))


# --------------------------------------------------------------- 96-well grid
#: Readings drawn per well in the grid; a cell is ~50 px wide, so more add nothing.
GRID_POINTS = 80
#: The plate grid and the open well sit side by side at this height, with the same
#: margins, so their plot areas are the same size and level.
CHART_HEIGHT = 460
CHART_MARGIN = dict(t=36, b=44)


def _thin(idx: list[int], n: int = GRID_POINTS) -> list[int]:
    """At most n of the indices, evenly spread, first and last kept."""
    if len(idx) <= n:
        return idx
    return [idx[int(round(k))] for k in np.linspace(0, len(idx) - 1, n)]


def plate_grid(plate: Plate, d: pd.DataFrame, selected: str | None = None,
               autoscale: bool = False) -> go.Figure:
    """The plate as an 8 x 12 grid of progress curves, drawn on one pair of axes.

    Each well owns a unit cell; its readings are scaled into it. Grey = reading,
    blue = used in the fit, orange = fitted rate (dashed = no linear phase).
    Every cell carries an invisible hit target: hover for the fit, click to open.
    ``selected`` is tinted through Plotly's own selection, which a click moves in the
    browser without the figure changing, so the chart is never rebuilt by a click.
    """
    d = d.set_index("well")
    t_max = plate.t[-1] if plate.t[-1] > 0 else 1.0
    t = plate.t / t_max
    shown = _thin(list(range(len(t))))
    lo, hi = np.nanmin(plate.a), np.nanmax(plate.a)

    xs, ys, fx, fy, ok_l, bad_l = [], [], [], [], ([], []), ([], [])
    shapes, hx, hy, wells = [], [], [], []
    for i, r in enumerate(ROWS):
        for c in COLS:
            well, x0, y0 = f"{r}{c}", c - 1, 7 - i
            f = d.loc[well]
            a = plate.a[:, (i * 12) + c - 1]
            if autoscale and np.isfinite(a).any():
                wlo, whi = np.nanmin(a), np.nanmax(a)
            else:
                wlo, whi = lo, hi
            span = (whi - wlo) or 1.0
            px = lambda tt: x0 + 0.07 + 0.86 * tt
            py = lambda aa: y0 + 0.1 + 0.8 * (aa - wlo) / span

            xs += list(px(t[shown])); ys += list(py(a[shown]))
            idx = list(f.idx)
            accepted = f.status in ACCEPTED
            if idx and accepted:
                used = _thin(idx, GRID_POINTS // 2)
                fx += list(px(t[used])); fy += list(py(a[used]))
            if idx and np.isfinite(f.vmax):
                ends = np.array([plate.t[min(idx)], plate.t[max(idx)]])
                line = f.vmax / 60 * ends + f.intercept
                lx, ly = ok_l if accepted else bad_l
                lx += list(px(ends / t_max)) + [None]
                ly += list(py(line)) + [None]

            edge = th.CONTROL_EDGE.get(f.role)
            shapes.append(dict(type="rect", x0=x0 + .03, x1=x0 + .97, y0=y0 + .03,
                               y1=y0 + .97, fillcolor=th.FIT_SHADE[f.status], layer="below",
                               line=dict(color=edge or "rgba(0,0,0,0)", width=2 if edge else 0)))
            hx.append(x0 + 0.5); hy.append(y0 + 0.5); wells.append(well)

    order = d.loc[wells]
    fig = go.Figure([
        go.Scattergl(x=xs, y=ys, mode="markers", name="reading", hoverinfo="skip",
                     marker=dict(size=2.5, color=th.UNUSED), **_KEEP),
        go.Scattergl(x=fx, y=fy, mode="markers", name="in fit window", hoverinfo="skip",
                     marker=dict(size=3.5, color=th.USED), **_KEEP),
        go.Scatter(x=ok_l[0], y=ok_l[1], mode="lines", name="fitted rate", hoverinfo="skip",
                   line=dict(color=th.LINE, width=1.6)),
        go.Scatter(x=bad_l[0], y=bad_l[1], mode="lines", name="no linear phase",
                   hoverinfo="skip", opacity=.55, line=dict(color=th.LINE, width=1, dash="dash")),
        go.Scatter(x=hx, y=hy, mode="markers", showlegend=False, customdata=wells,
                   marker=dict(size=46, symbol="square", color="rgba(0,0,0,0)"),
                   selectedpoints=[wells.index(selected)] if selected in wells else None,
                   selected=dict(marker=dict(color=th.SELECTED)),
                   unselected=dict(marker=dict(color="rgba(0,0,0,0)")),
                   text=hover_text(order.reset_index()), hovertemplate="%{text}<extra></extra>"),
    ])
    axis = dict(showgrid=False, zeroline=False, showline=False, ticks="", fixedrange=True)
    fig.update_xaxes(**axis, range=[-0.02, 12.02], side="top",
                     tickvals=[c - 0.5 for c in COLS], ticktext=[str(c) for c in COLS])
    # Wells stretch to fill the chart rather than stay square, so the grid always takes
    # the full CHART_HEIGHT and lines up with the open well beside it.
    fig.update_yaxes(**axis, range=[-0.02, 8.02],
                     tickvals=[7.5 - i for i in range(8)], ticktext=ROWS)
    fig.update_layout(shapes=shapes, height=CHART_HEIGHT, dragmode=False, plot_bgcolor=th.BG,
                      margin=dict(l=28, r=8, **CHART_MARGIN), hovermode="closest",
                      showlegend=False)
    return fig


# --------------------------------------------------------------- single well
def well_fit(plate: Plate, j: int, f: pd.Series, auto: dict | None = None,
             height: int = CHART_HEIGHT) -> go.Figure:
    """One progress curve, every reading lasso-selectable (trace 0, index = reading).

    ``auto`` is the automatic fit, drawn for comparison when ``f`` is manual.
    """
    t, a = plate.t / 60, plate.a[:, j]
    used = set(f.idx)
    colour = [th.USED if i in used else th.UNUSED for i in range(len(a))]
    fig = go.Figure(go.Scatter(
        x=t, y=a, mode="markers", name="reading (blue = in fit)",
        marker=dict(size=9, color=colour, line=dict(color="#FFFFFF", width=1)),
        hovertemplate="reading %{pointIndex}<br>%{x:.2f} min<br>A340 %{y:.4f}<extra></extra>",
        **_KEEP))

    def add_line(slope_min, intercept, idx, name, colour, dash, width, extend=True):
        lo, hi = t[min(idx)], t[max(idx)]
        fig.add_trace(go.Scatter(x=[lo, hi], y=[slope_min * lo + intercept,
                                                slope_min * hi + intercept],
                                 mode="lines", name=name, hoverinfo="skip",
                                 line=dict(color=colour, width=width, dash=dash)))
        if extend:   # where the line would run on to: shows the curve leaving it
            fig.add_trace(go.Scatter(x=[hi, t[-1]], y=[slope_min * hi + intercept,
                                                       slope_min * t[-1] + intercept],
                                     mode="lines", showlegend=False, hoverinfo="skip",
                                     line=dict(color=colour, width=1, dash="dot"), opacity=.5))

    if auto is not None and auto["idx"] and np.isfinite(auto["slope"]):
        add_line(auto["slope"] * 60, auto["intercept"], auto["idx"], "automatic fit",
                 th.INK2, "dash", 1.5, extend=False)
    if f.idx and np.isfinite(f.vmax):
        accepted = f.status in ACCEPTED
        add_line(f.vmax, f.intercept, f.idx,
                 "manual fit" if f.fit_source == "manual" else
                 ("fitted rate" if accepted else "5-point slope (no linear phase)"),
                 th.LINE, "solid" if accepted else "dash", 2.5)

    fig.update_xaxes(title_text="time (min)")
    fig.update_yaxes(title_text="A<sub>340</sub>")
    fig.update_layout(height=height, dragmode="lasso", margin=CHART_MARGIN,
                      plot_bgcolor="#FFFFFF", hovermode="closest", showlegend=False)
    return fig


# --------------------------------------------------------------- ranked rates
def ranked(d: pd.DataFrame, value: str, colours: dict[str, str], ref: float | None,
           ref_lab: str, ylab: str, y_range: list[float] | None = None,
           by: str = "plate") -> go.Figure:
    """Wells sorted by rate; hover a bar for its fit. ``by`` "plate" colours bars by plate
    (``colours``) with controls hatched, "role" colours them by sample type."""
    d = d.sort_values(value, ascending=False).reset_index(drop=True)
    wide = len(d) > 120
    if by == "plate":
        colour = d.plate.map(colours).fillna(th.OTHER_PLATE)
        pattern = dict(shape=d.role.map(th.CONTROL_PATTERN).tolist(), fgcolor="#FFFFFF",
                       size=5, solidity=0.45)
        key = {p: c for p, c in colours.items() if p in set(d.plate)}
        hatched = ["positive", "negative"]
    else:
        colour, pattern, hatched = d.role.map(th.ROLE_COLOUR), None, []
        key = {th.ROLE_LAB[r]: c for r, c in th.ROLE_COLOUR.items() if r in set(d.role)}
    fig = go.Figure(go.Bar(
        x=d.index, y=d[value], marker=dict(color=colour, line_width=0, pattern=pattern),
        width=1.0 if wide else 0.8, customdata=hover_text(d),
        hovertemplate="%{customdata}<extra></extra>", showlegend=False))

    if ref is not None and np.isfinite(ref):
        fig.add_hline(y=ref, line=dict(color=th.INK2, width=1.2, dash="dash"),
                      annotation_text=ref_lab, annotation_position="top right",
                      annotation_font=dict(size=11, color=th.INK2))

    _legend_key(fig, key, hatched)
    fig.update_yaxes(title_text=ylab, range=y_range)
    if wide:
        fig.update_xaxes(showticklabels=False, ticks="", title_text="wells ranked by rate",
                         range=[-4, len(d) + 4])
    else:
        fig.update_xaxes(tickvals=list(d.index), ticktext=list(d.well), tickangle=-90,
                         tickfont=dict(size=8), range=[-0.8, len(d) - 0.2])
    fig.update_layout(height=480, bargap=0.12 if not wide else 0, barmode="overlay")
    return fig


# --------------------------------------------------------------- QC
def _box(x, y, name, colour, hover, size=6, opacity=.6, show=True):
    return go.Box(x=x, y=y, name=name, marker=dict(color=colour, size=size, opacity=opacity),
                  line=dict(color=colour, width=1.2), boxpoints="all", jitter=.6,
                  pointpos=0, fillcolor="rgba(0,0,0,0)", customdata=hover,
                  hovertemplate="%{customdata}<extra></extra>", showlegend=show)


def controls_by_plate(fits: pd.DataFrame, plates: list[str], clocks: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for role, c in (("positive", th.POS), ("negative", th.NEG)):
        d = fits[fits.role == role]
        fig.add_trace(_box(d.plate.astype(str), d.vmax, th.ROLE_LAB[role], c, hover_text(d), 8))
    pos = fits[fits.role == "positive"].groupby("plate", observed=True).vmax.mean().mean()
    if np.isfinite(pos):
        fig.add_hline(y=pos, line=dict(color=th.POS, width=1.2, dash="dash"),
                      annotation_text=f"grand +ctrl mean {pos:.3f}",
                      annotation_position="top left", annotation_font=dict(size=11, color=th.INK2))
    fig.add_hline(y=0, line=dict(color=th.AXIS, width=1))
    fig.update_xaxes(categoryorder="array", categoryarray=plates, tickvals=plates,
                     ticktext=[f"{p}<br>{clocks.get(p, '')[:5]}" for p in plates])
    fig.update_yaxes(title_text=th.RATE_LAB)
    fig.update_layout(boxmode="group", height=420)
    return fig


# --------------------------------------------------------------- batch effects
def sample_distributions(fits: pd.DataFrame, value: str, ref: float,
                         ylab: str) -> go.Figure:
    smp = samples(fits)
    fig = go.Figure()
    for p, d in smp.groupby("plate", observed=True):
        fig.add_trace(_box([str(p)] * len(d), d[value], str(p),
                           th.SAMPLE, hover_text(d),
                           size=4, opacity=.45, show=False))
    fig.add_hline(y=ref, line=dict(color=th.INK2, width=1.1, dash="dash"))
    fig.update_yaxes(title_text=ylab)
    fig.update_layout(height=400, margin=dict(t=24))
    return fig


def plate_maps(fits: pd.DataFrame, value: str, label: str,
               pos_wells: list[str], neg_wells: list[str]) -> go.Figure:
    """Small multiples of the rate by physical position, one sequential scale."""
    plates = list(fits.plate.cat.categories)
    nc = min(5, len(plates))
    nr = -(-len(plates) // nc)
    lo, hi = np.nanpercentile(fits[value], [2, 98])
    fig = make_subplots(rows=nr, cols=nc, subplot_titles=plates,
                        horizontal_spacing=.03, vertical_spacing=.14 if nr > 1 else .1)
    for k, p in enumerate(plates):
        r, c = divmod(k, nc)
        d = fits[fits.plate == p]
        z = d.pivot_table(index="row", columns="col", values=value, aggfunc="first")
        lab = d.pivot_table(index="row", columns="col", values="label", aggfunc="first")
        z, lab = z.reindex(index=ROWS, columns=COLS), lab.reindex(index=ROWS, columns=COLS)
        fig.add_trace(go.Heatmap(z=z.values, x=COLS, y=ROWS, coloraxis="coloraxis",
                                 customdata=lab.values, xgap=1.5, ygap=1.5,
                                 hovertemplate="<b>%{customdata}</b><br>%{z:.3f}<extra></extra>"),
                      row=r + 1, col=c + 1)
        for wells, colour in ((pos_wells, th.POS), (neg_wells, th.NEG)):
            if wells:
                fig.add_trace(go.Scatter(
                    x=[int(w[1:]) for w in wells], y=[w[0] for w in wells], mode="markers",
                    marker=dict(symbol="square-open", size=13, color=colour, line_width=2),
                    hoverinfo="skip", showlegend=False), row=r + 1, col=c + 1)
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=8), ticks="", showgrid=False,
                     showline=False)
    fig.update_xaxes(tickvals=COLS, tickfont=dict(size=7), ticks="", showgrid=False,
                     showline=False)
    fig.update_annotations(font=dict(size=12, color=th.INK))
    fig.update_layout(height=max(320, 290 * nr), plot_bgcolor=th.BG,
                      coloraxis=dict(colorscale=th.SEQUENTIAL, cmin=lo, cmax=hi,
                                     colorbar=dict(title=dict(text=label, side="right"),
                                                   thickness=12, len=.85)))
    return fig


def spatial_marginals(fits: pd.DataFrame) -> go.Figure:
    """Row, column and edge effects, all plates pooled (normalised rates)."""
    smp = samples(fits)
    edge = np.where(is_edge(smp), "edge", "interior")
    fig = make_subplots(rows=1, cols=3, column_widths=[.3, .45, .25], horizontal_spacing=.06,
                        subplot_titles=("Row", "Column", "Edge vs interior"))
    for col, (key, order) in enumerate([(smp.row, ROWS), (smp.col, COLS),
                                        (edge, ["interior", "edge"])], start=1):
        for k in order:
            d = smp[np.asarray(key) == k]
            if d.empty:
                continue
            colour = th.SERIES[1] if k == "edge" else th.SERIES[0]
            fig.add_trace(_box([str(k)] * len(d), d.vmax_norm, str(k), colour,
                               hover_text(d), size=4, opacity=.4, show=False), row=1, col=col)
        fig.add_hline(y=smp.vmax_norm.median(), line=dict(color=th.INK2, width=1, dash="dash"),
                      row=1, col=col)
    fig.update_yaxes(title_text=th.NORM_LAB, row=1, col=1)
    fig.update_annotations(font=dict(size=12, color=th.INK))
    fig.update_layout(height=400)
    return fig
