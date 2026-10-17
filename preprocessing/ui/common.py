"""Chart colors, chart styling and small helpers shared by every tab of the test platform."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from layer1 import config as C
from layer1.pipeline import PipelineResult


@dataclass
class AppData:
    """What the sidebar worked out, handed to every tab."""

    R: PipelineResult
    nights: pd.DataFrame
    ml: pd.DataFrame
    main_sessions: pd.DataFrame
    chosen_night: date | None


# ---------------------------------------------------------------- chart styling
# Reference data-viz palette: sequential blue for sleep depth, categorical orange for
# highlights, status colors (always with a text label) for data quality.
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, BLUE_DARK, ORANGE = "#2a78d6", "#184f95", "#eb6834"
STAGE_COLORS = {
    "deep": "#104281",
    "core": "#3987e5",
    "rem": "#86b6ef",
    "asleep_unspecified": "#898781",
    "awake": ORANGE,
}
STAGE_LABELS = {
    "deep": "Deep",
    "core": "Core",
    "rem": "REM",
    "asleep_unspecified": "Asleep (no stage)",
    "awake": "Awake",
}
GOOD, WARNING, NO_DATA = "#0ca30c", "#fab219", "#d3d1c7"
DIVERGE_NEG, DIVERGE_POS = "#2a78d6", "#e34948"


def style(fig: go.Figure, height: int = 320, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=36, b=8),
        template="plotly_white",
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', size=13, color=INK2),
        paper_bgcolor="#fcfcfb",
        plot_bgcolor="#fcfcfb",
        hovermode="closest",
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None),
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False)
    return fig


def fmt_min(m) -> str:
    if m is None or pd.isna(m):
        return "–"
    m = int(round(m))  # round first, so 59.6 min shows as 1h 00m, never 0h 60m
    return f"{m // 60}h {m % 60:02d}m"


def settings(*names):
    rows = [{"setting": n, "value": str(getattr(C, n))} for n in names]
    with st.expander("Settings used in this step (change them in layer1/config.py)"):
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
