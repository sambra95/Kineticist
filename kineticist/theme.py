"""One colour scheme for every figure, mirrored in .streamlit/config.toml.

Importing this module registers and activates the ``kineticist`` Plotly template.
The role and series hues are the notebook's, validated for colour-vision
deficiency as a set (worst all-pairs dE 9.2 deutan, 19.2 normal vision).
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

# --- app chrome (same values as .streamlit/config.toml) ---------------------
BG = "#FAF8FF"
INK = "#1E1A2E"
INK2 = "#5C5470"             # secondary text, reference lines
GRID = "#ECE7FA"
AXIS = "#D9D0FB"
FONT = "Inter, Helvetica Neue, Helvetica, Arial, sans-serif"

# --- data roles ---------------------------------------------------------------
POS = "#1baf7a"              # positive control
NEG = "#eb6834"              # negative control (no enzyme)
SERIES = ["#2a78d6", "#c9358f", "#4a3aa7"]    # categorical hues, in this fixed order
SAMPLE = SERIES[0]           # sample wells

#: One hue per plate, in upload order and never cycled; validated as a set on the white
#: plot surface (worst adjacent dE 9.1 CVD, 19.6 normal vision). A ninth plate onward
#: folds to neutral, and the hover names every bar's plate.
PLATES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7",
          "#e34948"]
OTHER_PLATE = "#8a877f"
#: Controls keep their plate's hue and are told apart by hatching.
CONTROL_PATTERN = {"positive": "/", "negative": "x", "sample": ""}

UNUSED = "#a9a5b8"           # a reading outside the fit window
USED = "#2a78d6"             # a reading inside the fit window
LINE = "#eb6834"             # the fitted initial-rate line

#: 96-well grid: a panel is shaded by how its fit went...
FIT_SHADE = {"ok": "#D3F5DF",                  # good: an automatic linear fit
             "manual": "#E2D9FF",              # fitted by hand (the violet accent, pale)
             "no_linear_fit": "#FFDCD6",       # bad: no linear phase
             "insufficient_data": "#FFDCD6",   # bad: too few readings
             "excluded": "#E6E4EC"}            # marked "no fit" by hand: no rate
#: The open well's cell, tinted by Plotly in the browser when it is clicked.
SELECTED = "rgba(103, 65, 217, 0.28)"
#: ...and outlined only if it is a control.
CONTROL_EDGE = {"positive": POS, "negative": NEG}

#: Sequential ramp for magnitude (plate maps): one hue, light -> dark.
SEQUENTIAL = [[0, "#eef4fc"], [0.25, "#b7d3f6"], [0.5, "#6da7ec"],
              [0.75, "#2a78d6"], [1, "#104281"]]

def plate_colours(plates: list[str]) -> dict[str, str]:
    """Colour per plate, by position in the upload order, so a plate keeps its colour
    whichever plates are shown."""
    return {p: PLATES[i] if i < len(PLATES) else OTHER_PLATE for i, p in enumerate(plates)}


RATE_LAB = "V<sub>max</sub> (ΔA<sub>340</sub> min<sup>−1</sup>)"
NORM_LAB = "V<sub>max</sub> / plate +ctrl mean"
ROLE_LAB = {"positive": "positive control", "negative": "negative control",
            "sample": "sample"}
ROLE_COLOUR = {"positive": POS, "negative": NEG, "sample": SAMPLE}

#: Top navigation: the page tabs share the bar's full width. The bar is 53px by default,
#: shorter than a tab, so it is raised to keep the active tab's highlight inside it.
NAV_CSS = f"""<style>
.stAppHeader {{
    min-height: 72px;
    border-bottom: 1px solid {AXIS} !important;
    box-shadow: 0 2px 6px rgba(30, 26, 46, 0.06) !important;
}}
.stAppHeader .rc-overflow {{ width: 100%; gap: 10px; }}
.stAppHeader .rc-overflow-item {{ flex: 1 1 0; min-width: 0; }}
/* Space Streamlit keeps for the hidden Deploy button would push the tabs off centre. */
.stAppHeader div:has(> [data-testid="stToolbarActions"]) {{ min-width: auto; }}
.stAppHeader .rc-overflow-item > div,
.stAppHeader [data-testid="stTopNavLinkContainer"] {{ width: 100%; }}
.stAppHeader [data-testid="stTopNavLink"] {{
    width: 100%;
    justify-content: center;
    padding: 14px 4px !important;
}}
.stAppHeader [data-testid="stTopNavLink"] span {{ font-size: 1.2rem !important; }}
</style>"""


def _template() -> go.layout.Template:
    axis = dict(gridcolor=GRID, zeroline=False, linecolor=AXIS, ticks="outside",
                tickcolor=AXIS, title=dict(font=dict(size=12, color=INK2)),
                automargin=True)
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family=FONT, size=12, color=INK),
        paper_bgcolor=BG, plot_bgcolor="#FFFFFF",
        colorway=SERIES,
        title=dict(font=dict(size=15, color=INK), x=0, xanchor="left"),
        xaxis=axis, yaxis=axis,
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=AXIS, align="left",
                        font=dict(family=FONT, size=11, color=INK)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        margin=dict(l=64, r=24, t=48, b=48),
        boxgap=0.35,
    )
    return t


pio.templates["kineticist"] = _template()
pio.templates.default = "kineticist"
