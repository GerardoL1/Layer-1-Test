"""Tab 2: what cleaning removed and why."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from layer1 import config as C
from ui.common import (
    BLUE,
    INK2,
    MUTED,
    ORANGE,
    AppData,
    settings,
    style,
)


def render(data: AppData) -> None:
    R = data.R
    st.subheader("Clean")
    st.markdown(
        "Four rules, applied in order:\n"
        "1. **Apple Watch only.** Other apps (chest-strap apps, third-party sleep trackers) measure "
        "differently, so mixing them would add noise. iPhone **In Bed** times are kept; they're used for time in bed.\n"
        "2. **Exact duplicates** removed (sync glitches, re-imports).\n"
        "3. **Impossible values** removed, such as a heart rate of 12 or 250 from a loose strap.\n"
        "4. **Broken sleep pieces** removed: shorter than 30 seconds or longer than 16 hours.\n\n"
        "Apple Watch doesn't share raw motion or sensor signals, so there is no motion-artifact filtering "
        "to do here: HealthKit values are already processed by the watch."
    )
    if R.removal_log.empty:
        st.success("Nothing needed removing in this file.")
    else:
        st.markdown("**What was removed and why**")
        st.dataframe(
            R.removal_log.rename(columns={"data": "data type", "removed": "records removed"}),
            hide_index=True,
            use_container_width=True,
        )

    before = R.records.assign(data=R.records["stage"].fillna(R.records["metric"])).groupby("data").size()
    after = (
        pd.concat([v.assign(data=v["stage"].fillna(v["metric"])) for v in R.cleaned.values()]).groupby("data").size()
    )
    ba = pd.DataFrame({"before": before, "after": after}).fillna(0).astype(int)
    ba["removed"] = ba["before"] - ba["after"]
    st.markdown("**Before and after**")
    st.dataframe(
        ba.reset_index().rename(columns={"index": "data", "data": "data"}), hide_index=True, use_container_width=True
    )

    hr_removed = R.removed_rows[R.removed_rows["metric"] == "heart_rate"]
    hr_kept = R.cleaned["heart_rate"]
    if len(hr_kept):
        shown = hr_kept.sample(min(len(hr_kept), 15000), random_state=0).sort_values("start_local")
        fig = go.Figure()
        fig.add_trace(
            go.Scattergl(
                x=shown["start_local"],
                y=shown["value"],
                mode="markers",
                name="Kept",
                marker=dict(size=4, color=BLUE, opacity=0.35),
                hovertemplate="%{x|%b %d %H:%M}<br>%{y:.0f} bpm<extra>Kept</extra>",
            )
        )
        for reason, color, symbol in (
            ("Value outside plausible range", "#d03b3b", "x"),
            ("Not recorded by the Apple Watch", ORANGE, "diamond"),
            ("Exact duplicate", INK2, "circle-open"),
        ):
            part = hr_removed[hr_removed["reason"] == reason]
            if len(part):
                fig.add_trace(
                    go.Scattergl(
                        x=part["start_local"],
                        y=part["value"],
                        mode="markers",
                        name=f"Removed: {reason.lower()} ({len(part)})",
                        marker=dict(size=9, color=color, symbol=symbol, line=dict(width=1.5, color=color)),
                        hovertemplate="%{x|%b %d %H:%M}<br>%{y:.0f} bpm<extra>" + reason + "</extra>",
                    )
                )
        lo, hi = C.VALID_RANGES["heart_rate"]
        for y in (lo, hi):
            fig.add_hline(
                y=y,
                line=dict(color=MUTED, dash="dot", width=1),
                annotation_text=f"limit {y} bpm",
                annotation_position="top left",
                annotation_font_color=MUTED,
            )
        fig.update_yaxes(title="bpm")
        st.markdown("**Heart rate: kept vs removed**")
        st.plotly_chart(style(fig, 380), use_container_width=True)
        if len(hr_kept) > 15000:
            st.caption(f"Showing a random 15,000 of {len(hr_kept):,} kept readings; every removed reading is shown.")
    if len(R.removed_rows):
        with st.expander("Every removed record"):
            st.dataframe(
                R.removed_rows[["reason", "metric", "stage", "value", "source", "start_local", "end_local"]],
                hide_index=True,
                use_container_width=True,
            )
    settings(
        "WATCH_SOURCE_KEYWORDS",
        "IN_BED_SOURCE_KEYWORDS",
        "VALID_RANGES",
        "MIN_SLEEP_SEGMENT_SEC",
        "MAX_SLEEP_SEGMENT_HOURS",
    )
