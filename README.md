# Kineticist

Initial rates ("V<sub>max</sub>") from kinetic plate reads, with every
fit visible and correctable by hand. Built for NADP<sup>+</sup> → NADPH lysate screens
followed at A<sub>340</sub>, but any kinetic export in the same layout works.

## Run it

```bash
conda env create -f environment.yml     # once
conda activate kineticist
streamlit run streamlit_app.py
```

or, with uv: `uv run streamlit run streamlit_app.py`.

Drop one kinetic `.xlsx` export per plate into the sidebar. Plates are named **Plate 1**,
**Plate 2**, … in the order they were uploaded, and can be renamed there. Control wells
(default A1–A3 positive, A4–A6 no-enzyme) and the fit settings are set in the sidebar too.

## The pages

- **Fits** - each plate as a 96-well grid of progress curves: grey readings, blue
  readings used in the fit, the orange fitted rate (dashed where the well has no
  linear phase). Click a well to open it beside the grid, or step through wells
  with ← and →. **Lasso or box-select readings** on the well's curve and its rate
  is refitted through exactly those points at once, gaps allowed. A manual fit is
  outlined in indigo on the grid, shows the automatic fit dashed for comparison,
  and **Automatic fit** puts it back.
- **Rates** - wells ranked by V<sub>max</sub>, one plate at a time (shared y-axis) or
  all plates, raw or normalised to the plate's positive controls, bars coloured by
  plate or by sample type, and plate maps of rate by position.
- **Quality control** - controls and Z′ per plate, read QC (reads, interval,
  temperature, saturated readings, dropped partial sweeps), fit status by role, and
  batch effects: sample-well distributions per plate raw and normalised, and
  row/column/edge effects.
- **Export** - the per-well results and the per-plate summary as CSV. Manual fits are
  flagged (`fit_source = manual`) with the readings used (`fit_points`, 0 = first
  read) beside the automatic rate (`vmax_auto`).
- **About** - how rates are fitted, and how to read each page and its plots.

## How a rate is fitted

For each well, least squares of A<sub>340</sub> on time:

1. Fit the first 5 readings; that slope is the reference rate.
2. Add one reading at a time while R² ≥ 0.95 **and** the rate falls no more than 5 %
   below the reference (in the direction the trace runs, so falling traces work too).
3. The largest window passing both gives V<sub>max</sub> (ΔA<sub>340</sub> min<sup>−1</sup>).
4. If the first window already fails R², the well has no linear phase; its 5-point
   slope is reported but flagged.

The slope gate holds the window to the linear phase - these curves bend while
cumulative R² stays above 0.99. Rates are normalised as
`vmax / mean(+ctrl V-max on the same plate)`. No blank is subtracted: a constant
background drops out of a slope. "V<sub>max</sub>" is an initial rate, not a
Michaelis-Menten parameter.

## Layout

```
streamlit_app.py      entry point: page config, navigation, sidebar
session.py            Streamlit glue: inputs, caching, manual fits in session state
app_pages/            one script per page
kineticist/           the analysis, free of Streamlit
  reader.py           reading kinetic .xlsx exports
  fitting.py          automatic and manual initial-rate fits
  analysis.py         per-well table, controls, Z′, normalisation, batch statistics
  plots.py            every figure
  theme.py            colours and the Plotly template
tests/                pytest, on synthetic plates
```

`pytest` runs the analysis tests and renders every page headless.
