"""About: how rates are fitted, and how to read and use every page."""

import streamlit as st

from kineticist.fitting import FitSettings

# The current fit settings when plates are loaded, the defaults otherwise.
d = st.session_state.get("data")
s = d.settings if d is not None else FitSettings()

with st.container(border=True):
    st.subheader("How rates are fitted", anchor=False)
    st.markdown(f"""
**V<sub>max</sub>** here is the **initial rate** of the progress curve in
ΔA<sub>340</sub> min<sup>−1</sup>: the slope of a least-squares line through the
start of the trace. No substrate titration is involved, so it carries no
*k*<sub>cat</sub> or *K*<sub>M</sub> meaning.

1. Slide windows of **{s.min_points}** to **{2 * s.min_points}** readings across the
   trace and fit each one (a rolling slope).
2. Keep the windows with **R² ≥ {s.r2_threshold:.3f}**. The steepest of them, rising
   or falling, is the reference rate.
3. The longest kept window whose rate is no more than **{s.slope_tol:.0%}** below the
   reference gives V<sub>max</sub>.
4. If no window passes R², the well has **no linear phase**. The slope of its first
   {s.min_points} readings is still reported, but flagged.

The slope gate keeps the window in the linear phase: these curves bend while
R² is still above 0.99. A **manual fit** is a straight line through exactly the
readings you lasso, gaps allowed. Rates are normalised to the mean of the
plate's positive controls. No blank is subtracted, because a constant
background drops out of a slope.
""", unsafe_allow_html=True)

with st.container(border=True):
    st.subheader("Loading plates", anchor=False)
    st.markdown("""
Drop one kinetic `.xlsx` export per plate into the sidebar. Plates are named Plate 1,
Plate 2, ... in the order they were uploaded; rename them in the sidebar's plate table.
Control wells and the fit settings are set in the sidebar too. Nothing is analysed
until you click **Analyse**: changes made in the sidebar afterwards wait for the next
click, which fits every well afresh and discards all manual fits and no-fit marks.
""")

with st.container(border=True):
    st.subheader("Fits", anchor=False)
    st.markdown("""
- **Click a well** on the plate grid to open it beside the grid.
- **Lasso or box-select readings** on the open well's curve to refit its rate through
  exactly those points. The no-fit button marks a well as having no rate: its V-max
  is left empty (NaN) in every table and export, and it drops out of the control
  means. The reset button beside the well's status puts the automatic fit back.
- **On the grid**, each cell is shaded by how its fit went: green for a linear fit,
  violet for a manual fit, red for no linear phase or too few readings, grey for a
  well marked no fit. Positive
  controls are outlined green, negative controls orange.
- **On both plots**, grey points are readings, blue points are readings used in the
  fit, and the orange line is the fitted rate: dashed where the well has no linear
  phase. On a manual fit, the automatic fit is drawn dashed in grey for comparison.
- A failed automatic fit names the check it failed in its status badge, for example
  the R² of the initial window against the minimum. Like a well marked no fit, it has
  no rate: its V-max is left empty (NaN). The control statistics and Z′ still use each
  control's measured slope, since a no-enzyme control has no linear phase by design.
""")

with st.container(border=True):
    st.subheader("Rates", anchor=False)
    st.markdown("""
- On the ranked plot, **Colour by** switches the bars between two codings. By plate,
  each bar takes its plate's colour (a ninth plate onward is grey) and controls are
  hatched: diagonal lines for positive, a cross for negative. By sample type,
  positive controls are green, negative controls orange and samples blue.
- **Normalised** rates divide each well by the mean of its own plate's positive
  controls, so the controls sit at 1.
- The dashed line on the ranked plot is the positive-control mean: across plates for
  all plates, or the plate's own when one plate is shown.
- One plate at a time, the y-axis is shared across plates, so flipping between them
  compares like with like.
- **Plate maps** show rate by physical position; lighter is slower. Positive controls
  are outlined green, negative controls orange. The colour scale spans the 2nd–98th
  percentile.
""")

with st.container(border=True):
    st.subheader("Quality control", anchor=False)
    st.markdown("""
- **Z′** is computed per plate from the two control sets. Above 0.5 is an excellent
  assay, 0–0.5 marginal but usable.
- A no-enzyme well is expected to show no linear phase: it is flat to the reader's
  resolution, and its initial-window slope measures background drift.

**Batch effects** need two or more plates. Two things are worth separating: a
**plate-level technical offset** (lysate batch, substrate mix, reader drift, time on the
bench), which normalising to on-plate controls should remove, and a **real difference
in what the plates hold**, which it should not.

- The between-plate CV of the sample median, raw beside normalised, shows whether
  normalising removes a shared plate offset: if it does, the normalised CV is lower.
- The statistics and the spatial plots use sample wells only. The spatial plots pool
  all plates, use normalised rates, and draw the overall median as a dashed line.
""")

with st.container(border=True):
    st.subheader("Export", anchor=False)
    st.markdown("""
- Rates are in ΔA<sub>340</sub> min<sup>−1</sup>.
- `fit_source` is `manual` where you lassoed the fit or marked the well no fit
  (`status` `excluded`, with empty `vmax`); `vmax_auto` keeps the automatic
  rate beside it, and `fit_points` lists the readings used (0 = first read).
- The fit settings are carried as the last three columns.
- The filters change the preview only; a download is always every well.
""", unsafe_allow_html=True)
