"""Tab 5: missing nights, flags and which values are usable."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from layer1 import config as C
from ui.common import (
    GOOD,
    NO_DATA,
    WARNING,
    AppData,
    fmt_min,
    settings,
    style,
)


def render(data: AppData) -> None:
    nights = data.nights
    st.subheader("Missing data and quality flags")
    st.markdown(
        "Every calendar night gets a row, even nights with nothing recorded, so gaps are visible instead of silently "
        "skipped. Each value is then marked **usable** or not. Only usable values go into the personal baselines.\n"
        f"- **Sleep** is usable if the watch recorded at least {C.MIN_TST_FOR_USABLE_MIN / 60:g} hours.\n"
        "- **HRV** needs usable sleep plus at least one HRV reading in the window.\n"
        f"- **Overnight resting HR** needs usable sleep plus at least {C.MIN_HR_SAMPLES_PER_SLEEP_HOUR} heart rate "
        "readings per hour of sleep."
    )
    if not nights.empty:
        c = st.columns(4)
        c[0].metric("Calendar nights", len(nights))
        c[1].metric("Usable sleep", int(nights["usable_sleep"].sum()))
        c[2].metric("Usable HRV", int(nights["usable_hrv"].sum()))
        c[3].metric("Usable resting HR", int(nights["usable_rhr"].sum()))

        checks = [("Overnight resting HR", "usable_rhr"), ("HRV", "usable_hrv"), ("Sleep", "usable_sleep")]
        z, text = [], []
        for _label, col in checks:
            row_z, row_t = [], []
            for _, r in nights.iterrows():
                if r["flag_no_sleep_data"]:
                    row_z.append(0)
                    row_t.append("No data")
                elif r[col]:
                    row_z.append(2)
                    row_t.append("Usable")
                else:
                    row_z.append(1)
                    row_t.append("Flagged: " + (r["quality_notes"] or "not usable"))
            z.append(row_z)
            text.append(row_t)
        x = pd.to_datetime(nights["night_date"])
        fig = go.Figure(
            go.Heatmap(
                z=z,
                x=x,
                y=[c[0] for c in checks],
                text=text,
                xgap=2,
                ygap=2,
                colorscale=[[0, NO_DATA], [0.33, NO_DATA], [0.34, WARNING], [0.66, WARNING], [0.67, GOOD], [1, GOOD]],
                zmin=0,
                zmax=2,
                showscale=False,
                hovertemplate="%{x|%a %b %d}<br>%{y}: %{text}<extra></extra>",
            )
        )
        st.markdown("**Each night's data:** 🟩 usable · 🟨 flagged · ⬜ no data (hover a square for the reason)")
        fig.update_xaxes(showgrid=False, tickformat="%b %d")
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(style(fig, 230, legend=False), use_container_width=True)

        flagged = nights[nights["quality_notes"] != ""][
            ["night_date", "quality_notes", "tst_min", "hrv_count", "hr_night_count"]
        ]
        if len(flagged):
            st.markdown("**Flagged nights**")
            st.dataframe(
                flagged.assign(tst_min=flagged["tst_min"].map(fmt_min)), hide_index=True, use_container_width=True
            )
        else:
            st.success("Every night is complete.")
    settings("MIN_TST_FOR_USABLE_MIN", "MIN_HR_SAMPLES_PER_SLEEP_HOUR")
