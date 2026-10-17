"""Tab 6: personal baselines and z-scores."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from layer1 import config as C
from ui.common import (
    BLUE,
    DIVERGE_NEG,
    DIVERGE_POS,
    MUTED,
    AppData,
    settings,
    style,
)


def render(data: AppData) -> None:
    nights = data.nights
    st.subheader("Personal baselines and z-scores")
    st.markdown(
        f"Each night is compared with **the same person's previous {C.BASELINE_WINDOW_NIGHTS} nights** "
        f"(tonight is never part of its own baseline), using only usable values. A z-score appears once the "
        f"baseline has **at least {C.BASELINE_MIN_NIGHTS} usable values** and tonight's own value is usable.\n\n"
        "**z = (tonight − baseline mean) ÷ baseline SD.** The SD is the sample SD, but never less than "
        f"{C.MIN_SD_FRACTION_OF_MEAN:g} × the mean, so a very steady person's small wobbles don't turn into "
        "huge z-scores. 0 means a typical night for this person; −2 means well below "
        "their usual. HRV is log-transformed first because its values are skewed. Signs are left as they are: for "
        "resting HR and fragmentation, a high z is the *bad* direction."
    )
    if not nights.empty:
        label_to_col = {v[1]: k for k, v in C.ZSCORE_METRICS.items()}
        pick = st.selectbox("Metric", list(label_to_col))
        col = label_to_col[pick]
        zcol, _, gate = C.ZSCORE_METRICS[col]
        x = pd.to_datetime(nights["night_date"])
        val = nights[col].where(nights[gate].fillna(False).astype(bool))
        mu, sd = nights[f"{col}_base_mean"], nights[f"{col}_base_sd"]
        unit = {
            "hrv_ln": "ln(ms)",
            "rhr_night_bpm": "bpm",
            "tst_min": "minutes",
            "sleep_efficiency_pct": "%",
            "fragmentation_per_hr": "per hour",
        }[col]

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.62, 0.38], vertical_spacing=0.08)
        fig.add_trace(
            go.Scatter(x=x, y=mu + sd, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=mu - sd,
                mode="lines",
                line=dict(width=0),
                fill="tonexty",
                fillcolor="rgba(137,135,129,0.18)",
                name="Baseline ± 1 SD",
                hoverinfo="skip",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=mu,
                mode="lines",
                name="Baseline mean",
                line=dict(color=MUTED, width=2, dash="dash"),
                hovertemplate="%{x|%b %d}<br>baseline %{y:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=val,
                mode="lines+markers",
                name="Tonight",
                line=dict(color=BLUE, width=2),
                marker=dict(size=8, color=BLUE, line=dict(color="#fcfcfb", width=2)),
                connectgaps=False,
                hovertemplate="%{x|%b %d}<br>%{y:.2f} " + unit + "<extra></extra>",
            ),
            row=1,
            col=1,
        )
        zs = nights[zcol]
        fig.add_trace(
            go.Bar(
                x=x,
                y=zs,
                name="z-score",
                showlegend=False,
                marker_color=np.where(zs < 0, DIVERGE_NEG, DIVERGE_POS),
                hovertemplate="%{x|%b %d}<br>z = %{y:.2f}<extra></extra>",
            ),
            row=2,
            col=1,
        )
        for y in (-2, 2):
            fig.add_hline(y=y, line=dict(color=MUTED, dash="dot", width=1), row=2, col=1)
        fig.update_yaxes(title_text=unit, row=1, col=1)
        fig.update_yaxes(title_text="z", row=2, col=1)
        fig.update_xaxes(tickformat="%b %d")
        st.markdown(f"**{pick}: tonight vs personal baseline** (top) **and z-score** (bottom; dotted lines at ±2)")
        st.plotly_chart(style(fig, 480), use_container_width=True)
        first_z = nights.loc[zs.notna(), "night_date"].min()
        st.caption(
            "Gaps = nights where this value isn't usable. "
            + (
                f"First z-score on {pd.Timestamp(first_z):%b %d}; earlier nights are still building the baseline."
                if pd.notna(first_z)
                else "Not enough usable nights yet for any z-score."
            )
        )
        table = pd.DataFrame(
            {
                "night": nights["night_date"],
                "value": val.round(3),
                "baseline nights": nights[f"{col}_base_n"],
                "baseline mean": mu.round(3),
                "baseline SD": sd.round(3),
                "z": zs.round(2),
            }
        )
        st.dataframe(table, hide_index=True, use_container_width=True)
    settings("BASELINE_WINDOW_NIGHTS", "BASELINE_MIN_NIGHTS", "MIN_SD_FRACTION_OF_MEAN")
