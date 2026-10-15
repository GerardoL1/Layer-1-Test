"""Tab 4: nightly metrics for the chosen night (TST, efficiency, fragmentation, HRV, resting HR)."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from layer1 import config as C
from layer1 import pipeline as P
from ui.common import (
    BLUE,
    BLUE_DARK,
    INK,
    ORANGE,
    STAGE_COLORS,
    STAGE_LABELS,
    AppData,
    fmt_min,
    settings,
    style,
)


def render(data: AppData) -> None:
    R = data.R
    nights = data.nights
    main_sessions = data.main_sessions
    chosen_night = data.chosen_night
    st.subheader("Nightly metrics")
    st.markdown(
        "- **Total sleep time (TST)** = core + deep + REM minutes inside the window.\n"
        "- **Time in bed** = iPhone *In Bed* when it exists, otherwise onset to final awakening.\n"
        "- **Sleep efficiency** = TST ÷ time in bed × 100.\n"
        f"- **Fragmentation** = awakenings per hour of sleep (an awakening is ≥ {C.MIN_AWAKENING_MIN:g} min awake). "
        "This replaces *awake minutes ÷ time in bed*, which is just 100 − efficiency when there's no In Bed data.\n"
        "- **Overnight HRV** = mean of the SDNN readings inside the window (the watch takes only a few per night).\n"
        f"- **Overnight resting HR** = lowest {C.RHR_WINDOW_MIN}-minute average heart rate during sleep. "
        "Apple's own resting HR is a whole-day value, so it's shown only for comparison."
    )
    if chosen_night is not None:
        row = nights[nights["night_date"] == chosen_night].iloc[0]
        st.markdown(f"#### Night of {pd.Timestamp(chosen_night).strftime('%A %b %d')}")
        m = st.columns(6)
        m[0].metric("Total sleep", fmt_min(row["tst_min"]))
        m[1].metric("Efficiency", f"{row['sleep_efficiency_pct']:.1f}%", help=f"Time in bed from: {row['tib_source']}")
        m[2].metric(
            "Awakenings", f"{int(row['awakenings'])}", help=f"{row['fragmentation_per_hr']:.2f} per hour of sleep"
        )
        m[3].metric("Awake after onset", fmt_min(row["waso_min"]))
        m[4].metric(
            "Overnight HRV",
            "–" if pd.isna(row["hrv_night_ms"]) else f"{row['hrv_night_ms']:.1f} ms",
            help=f"{int(row['hrv_count'])} reading(s) that night",
        )
        m[5].metric(
            "Overnight resting HR",
            "–" if pd.isna(row["rhr_night_bpm"]) else f"{row['rhr_night_bpm']:.1f} bpm",
            help=f"Apple's daily value: {row['apple_rhr_bpm']:.0f} bpm" if pd.notna(row["apple_rhr_bpm"]) else None,
        )

        main = main_sessions[main_sessions["night_date"] == chosen_night].iloc[0]
        lo, hi = main["onset_utc"], main["wake_utc"]
        rhr = P.overnight_rhr(R.cleaned["heart_rate"], lo, hi)
        hr = R.cleaned["heart_rate"]
        pad = pd.Timedelta(minutes=45)
        around = hr[(hr["start_utc"] >= lo - pad) & (hr["start_utc"] <= hi + pad)]
        offset = main["onset_local"] - main["onset_utc"].tz_localize(None)  # UTC -> local for this night
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=around["start_local"],
                y=around["value"],
                mode="markers",
                name="Heart rate readings",
                marker=dict(size=6, color=BLUE, opacity=0.45),
                hovertemplate="%{x|%H:%M}<br>%{y:.0f} bpm<extra></extra>",
            )
        )
        if rhr["rolling"] is not None:
            roll = rhr["rolling"]
            full = roll.index - pd.Timedelta(minutes=C.RHR_WINDOW_MIN) >= lo
            r_ok = roll[full]
            fig.add_trace(
                go.Scatter(
                    x=r_ok.index.tz_localize(None) + offset,
                    y=r_ok["mean"],
                    mode="lines",
                    name=f"{C.RHR_WINDOW_MIN}-min rolling average",
                    line=dict(color=BLUE_DARK, width=2),
                    hovertemplate="%{x|%H:%M}<br>%{y:.1f} bpm<extra>rolling avg</extra>",
                )
            )
        if pd.notna(rhr["rhr_window_end_utc"]):
            end_local = rhr["rhr_window_end_utc"].tz_localize(None) + offset
            fig.add_vrect(
                x0=end_local - pd.Timedelta(minutes=C.RHR_WINDOW_MIN),
                x1=end_local,
                fillcolor=ORANGE,
                opacity=0.18,
                line_width=0,
            )
            fig.add_annotation(
                x=end_local - pd.Timedelta(minutes=C.RHR_WINDOW_MIN / 2),
                y=rhr["rhr_night_bpm"],
                text=f"Lowest {C.RHR_WINDOW_MIN}-min average: {rhr['rhr_night_bpm']:.1f} bpm",
                showarrow=True,
                arrowhead=0,
                ay=-40,
                font=dict(color=INK, size=12),
                bgcolor="#fcfcfb",
            )
        fig.add_vrect(x0=main["onset_local"], x1=main["wake_local"], fillcolor=BLUE, opacity=0.05, line_width=0)
        fig.update_xaxes(tickformat="%H:%M")
        fig.update_yaxes(title="bpm")
        st.markdown("**Overnight heart rate** (shaded blue = sleep window, orange = lowest 30-minute stretch)")
        st.plotly_chart(style(fig, 340), use_container_width=True)

        hrv = R.cleaned["hrv_sdnn"]
        night_hrv = hrv[(hrv["start_utc"] >= lo) & (hrv["start_utc"] <= hi)]
        if len(night_hrv):
            st.markdown("**HRV readings used tonight**")
            st.dataframe(
                pd.DataFrame(
                    {"time": night_hrv["start_local"].dt.strftime("%H:%M"), "SDNN (ms)": night_hrv["value"].round(1)}
                ),
                hide_index=True,
            )
        else:
            st.warning("No HRV reading inside tonight's sleep window, so HRV is missing for this night.")

    st.markdown("#### Every night")
    has = nights[nights["tst_min"].notna()]
    fig = go.Figure()
    for stage, col in (
        ("deep", "deep_min"),
        ("core", "core_min"),
        ("rem", "rem_min"),
        ("asleep_unspecified", "unspecified_min"),
    ):
        if has[col].fillna(0).sum() == 0:
            continue
        fig.add_trace(
            go.Bar(
                x=pd.to_datetime(has["night_date"]),
                y=has[col] / 60,
                name=STAGE_LABELS[stage],
                marker=dict(color=STAGE_COLORS[stage], line=dict(color="#fcfcfb", width=1)),
                hovertemplate="%{x|%b %d}<br>%{y:.1f} h<extra>" + STAGE_LABELS[stage] + "</extra>",
            )
        )
    fig.update_layout(barmode="stack", bargap=0.25)
    st.markdown("**Total sleep time by stage**")
    fig.update_yaxes(title="hours")
    st.plotly_chart(style(fig, 320), use_container_width=True)
    show = nights[
        [
            "night_date",
            "tst_min",
            "deep_min",
            "rem_min",
            "waso_min",
            "awakenings",
            "tib_min",
            "tib_source",
            "sleep_efficiency_pct",
            "fragmentation_per_hr",
            "hrv_night_ms",
            "hrv_count",
            "rhr_night_bpm",
            "apple_rhr_bpm",
        ]
    ].copy()
    st.dataframe(show.round(2), hide_index=True, use_container_width=True)
    settings("MIN_AWAKENING_MIN", "RHR_WINDOW_MIN", "RHR_MIN_SAMPLES_IN_WINDOW", "HRV_LOG_TRANSFORM")
