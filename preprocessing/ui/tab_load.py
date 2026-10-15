"""Tab 1: what the export holds and what Layer 1 keeps."""

import numpy as np
import streamlit as st

from ui.common import (
    AppData,
    settings,
)


def render(data: AppData) -> None:
    R = data.R
    st.subheader("Load the export")
    st.markdown(
        "The export holds every type of Health data. Layer 1 only needs **heart rate, Apple's resting "
        "heart rate, HRV (SDNN) and sleep**, so everything else is skipped while reading. "
        "Each record keeps its UTC time (for ordering and durations) and its local clock time "
        "(to decide which night it belongs to)."
    )
    first, last = R.records["start_local"].min(), R.records["end_local"].max()
    c1, c2, c3 = st.columns(3)
    c1.metric("From", first.strftime("%b %d, %Y"))
    c2.metric("To", last.strftime("%b %d, %Y"))
    c3.metric("Record types in file", len(R.type_counts))
    left, right = st.columns([3, 2])
    with left:
        tc = R.type_counts.copy()
        tc["type"] = tc["type"].str.replace("HKQuantityTypeIdentifier", "").str.replace("HKCategoryTypeIdentifier", "")
        tc["used for Layer 1"] = np.where(tc["kept"], "yes", "skipped")
        st.markdown("**Everything in the file**")
        st.dataframe(tc[["type", "records", "used for Layer 1"]], hide_index=True, use_container_width=True)
    with right:
        st.markdown("**What was kept, by source**")
        kept = R.records.assign(data=R.records["stage"].fillna(R.records["metric"]))
        st.dataframe(
            kept.groupby(["data", "source"]).size().rename("records").reset_index(),
            hide_index=True,
            use_container_width=True,
        )
    with st.expander("First 200 raw records"):
        st.dataframe(
            R.records.head(200)[["metric", "stage", "value", "unit", "source", "start_local", "end_local"]],
            hide_index=True,
            use_container_width=True,
        )
    settings("DEFAULT_DAYS")
