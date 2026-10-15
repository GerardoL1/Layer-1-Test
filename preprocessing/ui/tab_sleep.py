"""Tab 3: sleep pieces, sessions and the main sleep window for the chosen night."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from layer1 import config as C
from ui.common import (
    BLUE,
    BLUE_DARK,
    MUTED,
    STAGE_COLORS,
    STAGE_LABELS,
    AppData,
    fmt_min,
    settings,
    style,
)


def render(data: AppData) -> None:
    R = data.R
    chosen_night = data.chosen_night
    st.subheader("Find the main sleep window")
    st.markdown(
        f"Sleep arrives as many short pieces (core, deep, REM, awake). Pieces less than "
        f"**{C.SESSION_GAP_MIN} minutes** apart are joined into one **session**. Each session's window runs "
        f"from **sleep onset** (first asleep piece) to **final awakening** (last asleep piece); awake time "
        f"before onset or after final awakening doesn't count. The **longest session** of each night is the "
        f"main sleep; any others are **naps** and are ignored. A night is named after the evening it starts."
    )
    n_main = int(R.sessions["is_main"].sum()) if not R.sessions.empty else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("Sessions found", len(R.sessions))
    c2.metric("Main sleeps", n_main)
    c3.metric("Naps ignored", len(R.sessions) - n_main)

    if chosen_night is not None:
        night_sessions = R.sessions[R.sessions["night_date"] == chosen_night]
        main = night_sessions[night_sessions["is_main"]].iloc[0]
        st.markdown(f"#### Night of {pd.Timestamp(chosen_night).strftime('%A %b %d')}")
        g = R.stages[R.stages["session_id"].isin(night_sessions["session_id"])]
        ib = R.cleaned["in_bed"]
        pad = pd.Timedelta(hours=C.IN_BED_MATCH_HOURS)
        ib = ib[(ib["end_utc"] > main["onset_utc"] - pad) & (ib["start_utc"] < main["wake_utc"] + pad)]

        levels = {"in_bed": 5, "awake": 4, "rem": 3, "core": 2, "asleep_unspecified": 2, "deep": 1}
        fig = go.Figure()
        for stage in ("deep", "core", "asleep_unspecified", "rem", "awake"):
            part = g[g["stage"] == stage]
            if part.empty:
                continue
            xs, ys, text = [], [], []
            for s_, e_ in zip(part["start_local"], part["end_local"]):
                mins = (e_ - s_).total_seconds() / 60
                xs += [s_, e_, None]
                ys += [levels[stage]] * 2 + [None]
                text += [f"{STAGE_LABELS[stage]}: {mins:.0f} min"] * 2 + [None]
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    name=STAGE_LABELS[stage],
                    line=dict(color=STAGE_COLORS[stage], width=14),
                    hovertext=text,
                    hoverinfo="text+x",
                )
            )
        if len(ib):
            xs, ys = [], []
            for s_, e_ in zip(ib["start_local"], ib["end_local"]):
                xs += [s_, e_, None]
                ys += [5, 5, None]
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    name="In bed (iPhone)",
                    line=dict(color=MUTED, width=8),
                    hoverinfo="x+name",
                )
            )
        has_ib = len(ib) > 0
        fig.add_vrect(x0=main["onset_local"], x1=main["wake_local"], fillcolor=BLUE, opacity=0.07, line_width=0)
        for x, lbl, anchor, shift in (
            (main["onset_local"], "Sleep onset", "left", 6),
            (main["wake_local"], "Final awakening", "right", -6),
        ):
            fig.add_vline(x=x, line=dict(color=BLUE_DARK, width=1.5, dash="dash"))
            fig.add_annotation(
                x=x,
                y=5.65 if has_ib else 4.75,
                text=f"{lbl} {x:%H:%M}",
                showarrow=False,
                xanchor=anchor,
                xshift=shift,
                font=dict(color=BLUE_DARK, size=12),
            )
        for _, nap in night_sessions[~night_sessions["is_main"]].iterrows():
            fig.add_vrect(
                x0=nap["onset_local"],
                x1=nap["wake_local"],
                fillcolor=MUTED,
                opacity=0.12,
                line_width=0,
                annotation_text="nap (ignored)",
                annotation_position="top left",
            )
        fig.update_yaxes(
            tickvals=[1, 2, 3, 4, 5] if has_ib else [1, 2, 3, 4],
            ticktext=["Deep", "Core", "REM", "Awake", "In bed"] if has_ib else ["Deep", "Core", "REM", "Awake"],
            range=[0.4, 6.1] if has_ib else [0.4, 5.1],
            showgrid=False,
        )
        x0 = min([main["onset_local"]] + list(ib["start_local"]) + list(night_sessions["onset_local"])) - pd.Timedelta(
            minutes=30
        )
        x1 = max([main["wake_local"]] + list(ib["end_local"]) + list(night_sessions["wake_local"])) + pd.Timedelta(
            minutes=30
        )
        fig.update_xaxes(tickformat="%H:%M", range=[x0, x1])
        st.plotly_chart(style(fig, 360), use_container_width=True)
        st.caption("Shaded area = the detected sleep window used for every metric in the next step.")

        sess = night_sessions.assign(
            role=np.where(night_sessions["is_main"], "main sleep", "nap"),
            start=night_sessions["onset_local"].dt.strftime("%a %H:%M"),
            end=night_sessions["wake_local"].dt.strftime("%a %H:%M"),
            asleep=night_sessions["asleep_min"].map(fmt_min),
        )
        st.dataframe(sess[["role", "start", "end", "asleep"]], hide_index=True, use_container_width=True)
    with st.expander("All sessions"):
        if not R.sessions.empty:
            st.dataframe(
                R.sessions.assign(asleep=R.sessions["asleep_min"].map(fmt_min))[
                    ["night_date", "is_main", "onset_local", "wake_local", "asleep"]
                ],
                hide_index=True,
                use_container_width=True,
            )
    settings("SESSION_GAP_MIN", "NIGHT_SHIFT_HOURS", "IN_BED_MATCH_HOURS")
