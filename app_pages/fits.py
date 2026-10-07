"""Fits: each plate as a 96-well grid. Click a well to open it; lasso readings to refit."""

import numpy as np
import streamlit as st

import session
from kineticist import plots
from kineticist.fitting import why_no_fit
from kineticist.reader import WELLS

d = session.require()
plates = list(d.plates)
if st.session_state.get("plate") not in plates:
    st.session_state.plate = plates[0]
st.session_state.setdefault("well", "A1")

#: status -> badge label, colour, icon
STATUS = {"ok": ("Linear fit", "green", ":material/check:"),
          "manual": ("Manual fit", "violet", ":material/edit:"),
          "no_linear_fit": ("No linear phase", "orange", ":material/warning:"),
          "insufficient_data": ("Too few readings", "red", ":material/error:"),
          "excluded": ("No fit", "gray", ":material/block:")}

#: role -> suffix in the well picker (a sample needs none)
ROLE = {"positive": "· +ctrl", "negative": "· −ctrl", "sample": ""}

#: Room the info cards take under the well's chart, so that card and chart together
#: are as tall as the plate grid beside them.
CARDS_HEIGHT = 175

GRID_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": [
    "zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d", "autoScale2d",
    "resetScale2d"]}
WELL_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["autoScale2d"]}


def pick_well(key: str) -> None:
    """A click on the grid opens that well."""
    points = st.session_state[key].selection.points
    if points and points[0].get("customdata"):
        st.session_state.well = points[0]["customdata"]
        st.session_state.grid_clicked = True


def refit(plate: str, well: str, key: str) -> None:
    """Lassoed readings become the well's fit window."""
    points = st.session_state[key].selection.points
    idx = {p["point_index"] for p in points if p["curve_number"] == 0}
    if len(idx) >= 3:
        session.set_override(plate, well, tuple(idx))
    elif points:
        st.toast("Select at least three readings to fit a rate.", icon=":material/info:")
    st.session_state.nonce += 1              # clear the lasso outline off the chart


def fmt(v: float, spec: str) -> str:
    return format(v, spec) if np.isfinite(v) else "–"


def stat(col, label: str, value: str, note: str | None = None) -> None:
    """A compact info card: small label over a bold value, with an optional grey note."""
    with col.container(gap="xxsmall"):
        st.caption(label)
        st.markdown(f"**{value}**" + (f" :gray[· {note}]" if note else ""))


def failed_check(plate: str, j: int) -> str:
    """The check a failed automatic fit did not pass, in a few words for its badge."""
    p, m = d.plates[plate], d.settings.min_points
    why = why_no_fit(p.t, p.a[:, j], d.settings)
    if why["check"] == "short":
        return f"Only {why['n_available']} of {m} readings"
    if why["check"] == "flat":
        return "Readings flat"
    return f"Best R² {why['r2_0']:.3f} < {d.settings.r2_threshold:.3f}"


@st.fragment
def workspace() -> None:
    fits = session.fits(d)
    plate = st.session_state.plate
    sub = fits[fits.plate == plate]
    by_well = sub.set_index("well")
    well = st.session_state.well
    # The grid outlines the open well through Plotly's own selection, which a click moves
    # in the browser. Redrawn from here only when the well changed some other way
    # (picker, plate, refit), the figure is untouched by a click, so the chart is never
    # rebuilt under the pointer and the next click always lands.
    if not st.session_state.pop("grid_clicked", False):
        st.session_state.grid_anchor = well
    f = by_well.loc[well]
    nonce = st.session_state.nonce
    manual = f.fit_source == "manual"
    excluded = f.status == "excluded"
    j = WELLS.index(well)

    # Plate and well side by side, each card a one-row header of controls over its
    # chart; the charts share a height and margins, so the plots line up.
    grid_col, well_col = st.columns([1.55, 1], gap="medium", border=True)
    with grid_col:
        with st.container(horizontal=True, vertical_alignment="center", gap="medium"):
            st.selectbox("Plate", plates, key="plate", label_visibility="collapsed",
                         width=160)
            st.space("stretch")
            st.toggle("Scale each well to its own trace", key="autoscale",
                      help="Off: one absorbance scale across the plate, so wells "
                           "compare directly. On: each well fills its cell, "
                           "better for judging weak wells.")
        key = f"grid-{nonce}"
        st.plotly_chart(plots.plate_grid(d.plates[plate], sub, st.session_state.grid_anchor,
                                         st.session_state.get("autoscale", False)),
                        key=key, on_select=lambda: pick_well(key),
                        selection_mode="points", config=GRID_CONFIG)

    with well_col:
        label, colour, icon = STATUS[f.status]
        if f.status in ("no_linear_fit", "insufficient_data"):
            label = failed_check(plate, j)
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            st.selectbox("Well", WELLS, key="well", label_visibility="collapsed", width=130,
                         format_func=lambda w: f"{w} {ROLE[by_well.role[w]]}".strip())
            st.badge(label, icon=icon, color=colour)
            st.space("stretch")
            st.button("", icon=":material/block:", disabled=excluded,
                      on_click=session.set_no_fit, args=(plate, well),
                      help="No fit: this well has no rate (V-max is left empty)")
            st.button("", icon=":material/restart_alt:", disabled=not manual,
                      on_click=session.clear_override, args=(plate, well),
                      help="Automatic fit: discard the manual fit or no-fit mark "
                           "for this well")
        auto = session.autos(d)[plate][j] if manual else None
        lkey = f"lasso-{plate}-{well}-{nonce}"
        st.plotly_chart(plots.well_fit(d.plates[plate], j, f, auto,
                                       height=plots.CHART_HEIGHT - CARDS_HEIGHT), key=lkey,
                        on_select=lambda: refit(plate, well, lkey),
                        selection_mode=("lasso", "box"), config=WELL_CONFIG)
        (vmax, norm), (r2, n) = (st.columns(2, gap="xsmall", border=True) for _ in "ab")
        stat(vmax, "V-max, ΔA₃₄₀/min", fmt(f.vmax, "+.4f"),
             f"{f.vmax - f.vmax_auto:+.4f} vs auto"
             if manual and np.isfinite(f.vmax - f.vmax_auto) else None)
        stat(norm, "Normalised to +ctrl", fmt(f.vmax_norm, ".3f"))
        stat(r2, "R²", fmt(f.r2, ".4f"))
        stat(n, "Readings in fit",
         f"{f.n_points} to {fmt(f.t_end_s, '.0f')} s" if f.n_points else "–")


workspace()
