"""Export: the per-well results and the per-plate summary as CSV."""

import streamlit as st

import session
from kineticist import analysis

d = session.require()
fits = session.fits(d)
NUM = st.column_config.NumberColumn

table = analysis.export_table(fits).assign(
    min_points=d.settings.min_points, r2_threshold=d.settings.r2_threshold,
    slope_tol=d.settings.slope_tol)
summary = analysis.plate_summary(fits)
day = next((p.started.strftime("%Y%m%d") for p in d.plates.values() if p.started), "")
stem = f"kineticist_{day}" if day else "kineticist"

wells, plates = st.columns(2, gap="medium")
wells.download_button("Per-well results", table.to_csv(index=False).encode(),
                      f"{stem}_well_vmax.csv", "text/csv", type="primary",
                      icon=":material/download:", width="stretch")
plates.download_button("Plate summary", summary.to_csv().encode(),
                       f"{stem}_plate_summary.csv", "text/csv",
                       icon=":material/download:", width="stretch")

show = st.pills("Show", ["Samples", "Controls", "No linear phase", "Manual fits"],
                selection_mode="multi", key="export_filter",
                help="Filters the preview only; the download is always every well.")

view = table
if "Samples" in show and "Controls" not in show:
    view = view[view.role == "sample"]
if "Controls" in show and "Samples" not in show:
    view = view[view.role != "sample"]
if "No linear phase" in show:
    view = view[view.status == "no_linear_fit"]
if "Manual fits" in show:
    view = view[view.fit_source == "manual"]

st.dataframe(
    view, hide_index=True, height=560,
    column_config={
        "label": st.column_config.TextColumn("Well", pinned=True),
        "vmax": NUM("V-max (ΔA/min)", format="%+.4f"),
        "se": NUM("SE", format="%.5f"),
        "vmax_norm": NUM("Normalised", format="%.3f"),
        "vmax_norm_se": NUM("Normalised SE", format="%.3f"),
        "vmax_auto": NUM("Automatic V-max", format="%+.4f"),
        "vmax_initial": NUM("Initial-window V-max", format="%+.4f"),
        "r2": NUM("R²", format="%.4f"),
        "fit_points": st.column_config.TextColumn(
            "Readings fitted", help="Reading indices in the fit, 0 = first read"),
    })
st.caption(f"{len(view)} of {len(table)} wells shown.")
