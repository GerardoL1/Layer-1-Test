"""Tab 7: the ML-ready table and its column dictionary."""

import streamlit as st

from layer1 import pipeline as P
from ui.common import (
    AppData,
)


def render(data: AppData) -> None:
    R = data.R
    nights = data.nights
    ml = data.ml
    st.subheader("ML-ready table")
    st.markdown(
        "One row per night for this person, in a fixed column order. Nights with missing data stay in the "
        "table with their flags, so the model step can decide how to handle them. "
        "`readiness_label` is an **empty placeholder** for the training label you'll collect later."
    )
    c = st.columns(4)
    c[0].metric("Rows (nights)", len(ml))
    c[1].metric("Columns", ml.shape[1])
    c[2].metric("Rows with z-scores", int(ml[["z_hrv", "z_rhr", "z_tst"]].notna().any(axis=1).sum()) if len(ml) else 0)
    c[3].metric(
        "Fully usable rows", int((ml["usable_sleep"] & ml["usable_hrv"] & ml["usable_rhr"]).sum()) if len(ml) else 0
    )
    st.dataframe(ml, hide_index=True, use_container_width=True, height=420)
    safe = "".join(ch for ch in R.person_id if ch.isalnum() or ch in "-_") or "tester"
    st.download_button(
        "Download ML-ready CSV",
        ml.to_csv(index=False).encode("utf-8"),
        file_name=f"layer1_features_{safe}.csv",
        mime="text/csv",
        type="primary",
    )
    with st.expander("What every column means"):
        st.dataframe(P.column_dictionary(), hide_index=True, use_container_width=True)
    with st.expander("Everything computed (all intermediate columns)"):
        st.dataframe(nights, hide_index=True, use_container_width=True)
        st.download_button(
            "Download full nightly table",
            nights.to_csv(index=False).encode("utf-8"),
            file_name=f"layer1_full_{safe}.csv",
            mime="text/csv",
        )
