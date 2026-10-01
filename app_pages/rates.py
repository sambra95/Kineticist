"""Rates: wells ranked by V-max, plate by plate or across all plates, and plate maps."""

import streamlit as st

import session
from kineticist import analysis, plots, theme

d = session.require()
fits = session.fits(d)
ctrl = analysis.controls(fits)
ALL = "All plates"
colours = theme.plate_colours(list(d.plates))

with st.container(horizontal=True, vertical_alignment="bottom", gap="medium"):
    view = st.selectbox("Plate", [ALL, *d.plates], key="rates_plate", width=220)
    scale = st.segmented_control("Scale", ["Raw", "Normalised"], default="Raw",
                                 key="rates_scale", required=True)
    colour_by = st.segmented_control("Colour by", ["Plate", "Sample type"], default="Plate",
                                     key="rates_colour", required=True)

norm = scale == "Normalised"
by = "plate" if colour_by == "Plate" else "role"
value, ylab = ("vmax_norm", theme.NORM_LAB) if norm else ("vmax", theme.RATE_LAB)
if norm and ctrl.pos_mean.isna().all():
    st.warning("No positive-control wells are set, so there is nothing to normalise to.",
               icon=":material/warning:")
    st.stop()

shown = fits if view == ALL else fits[fits.plate == view]
with st.container(border=True):
    if view == ALL:
        ref = 1.0 if norm else ctrl.pos_mean.mean()
        st.subheader(f"All {len(fits)} wells ranked by V-max", anchor=False)
        fig = plots.ranked(fits, value, colours, ref,
                           "+ctrl = 1" if norm else f"mean +ctrl {ref:.3f}", ylab, by=by)
    else:
        c = ctrl.loc[view]
        ref = 1.0 if norm else c.pos_mean
        st.subheader(f"{view} ranked by V-max", anchor=False)
        st.caption(f"Read {c.clock[:5] or '–'} · Z′ = {c.zprime:.2f} · +ctrl mean "
                   f"{c.pos_mean:.4f}")
        lo, hi = min(0.0, fits[value].min() * 1.08), fits[value].max() * 1.06
        fig = plots.ranked(shown, value, colours, ref,
                           "+ctrl = 1" if norm else f"+ctrl {ref:.3f}", ylab, [lo, hi], by)
    st.plotly_chart(fig, key="ranked")

s = analysis.samples(shown)
with st.container(horizontal=True):
    st.metric("Sample median", f"{s[value].median():.3f}", border=True)
    st.metric("Sample range", f"{s[value].min():.3f} to {s[value].max():.3f}", border=True)
    above = (s.vmax_norm >= 1).sum()
    st.metric("At or above the plate +ctrl", f"{above} of {len(s)}", border=True)

with st.container(border=True):
    st.subheader("Plate maps", anchor=False)
    st.plotly_chart(plots.plate_maps(fits, value, ylab, d.pos, d.neg), key="maps")
