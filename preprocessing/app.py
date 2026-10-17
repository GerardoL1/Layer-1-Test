"""
Layer 1 preprocessing test platform.

    streamlit run app.py

Pick a sample file or upload an Apple Health export, then walk through the
tabs to see what each preprocessing step does. The last tab is the ML-ready table.
"""

import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from ui import (
    tab_baselines,
    tab_clean,
    tab_daily,
    tab_load,
    tab_metrics,
    tab_ml_table,
    tab_quality,
    tab_sleep,
)
from ui.common import AppData

from layer1 import pipeline as P

HERE = Path(__file__).parent
SAMPLES = {
    "Alex: hard training block at the end": ("mock_export_alex_overreach.zip", "alex"),
    "Sam: steady and well recovered": ("mock_export_sam_steady.zip", "sam"),
    "Jordan: messy real-world data": ("mock_export_jordan_messy.zip", "jordan"),
}

# ---------------------------------------------------------------- running the pipeline


@st.cache_data(show_spinner=False, max_entries=6)
def run_from_bytes(data: bytes, name: str, person: str, days):
    buf = io.BytesIO(data)
    buf.name = name
    return P.run_pipeline(buf, person, days)


@st.cache_data(show_spinner=False, max_entries=6)
def run_from_path(path: str, mtime: float, person: str, days):
    return P.run_pipeline(path, person, days)


st.set_page_config(page_title="Layer 1 preprocessing", page_icon="🫀", layout="wide")

with st.sidebar:
    st.header("Input")
    mode = st.radio(
        "Data source",
        ["Sample file", "Upload an export", "File path on this computer"],
        help="Exports over ~200 MB are faster to load with the file path option.",
    )
    data_bytes = data_name = path = None
    default_person = "tester1"
    if mode == "Sample file":
        label = st.selectbox("Sample", list(SAMPLES))
        fname, default_person = SAMPLES[label]
        path = str(HERE / "sample_data" / fname)
    elif mode == "Upload an export":
        up = st.file_uploader("export.zip or export.xml from the Health app", type=["zip", "xml"])
        if up is not None:
            data_bytes, data_name = up.getvalue(), up.name
    else:
        path = st.text_input("Full path to export.zip", placeholder=r"C:\Users\you\Downloads\export.zip")
        path = path.strip().strip('"') or None

    person = st.text_input("Tester name", value=default_person)
    days_choice = st.selectbox(
        "How far back",
        ["30 days", "60 days", "90 days", "180 days", "1 year", "Everything"],
        index=2,
        help="Counted back from the newest record in the file.",
    )
    days = {"30 days": 30, "60 days": 60, "90 days": 90, "180 days": 180, "1 year": 365}.get(days_choice)

st.title("Layer 1 preprocessing")
st.caption(
    "Apple Health export → cleaned data → nightly metrics → personal baselines → one ML-ready row per night. "
    "Nothing is trained here."
)

if data_bytes is None and path is None:
    st.info("Choose a sample file or upload an export in the sidebar to start.")
    st.stop()
if path is not None and not os.path.exists(path):
    st.error(f"No file at {path}. Check the path and try again.")
    st.stop()

try:
    with st.spinner("Reading the export and running every step…"):
        if data_bytes is not None:
            R = run_from_bytes(data_bytes, data_name, person, days)
        else:
            R = run_from_path(path, os.path.getmtime(path), person, days)
except Exception as e:  # show parsing problems in plain words
    st.error(f"Couldn't process this file: {e}")
    st.stop()

for note in R.notes:
    st.warning(note)

nights, ml = R.nights, R.ml_table
main_sessions = R.sessions[R.sessions["is_main"]] if not R.sessions.empty else R.sessions
night_options = list(nights.loc[nights["tst_min"].notna(), "night_date"]) if not nights.empty else []

with st.sidebar:
    st.header("Inspect a night")
    if night_options:
        default_idx = len(night_options) - 1
        chosen_night = st.selectbox(
            "Night of",
            night_options,
            index=default_idx,
            format_func=lambda d: pd.Timestamp(d).strftime("%a %b %d, %Y"),
            help="Used by the Sleep window and Nightly metrics tabs.",
        )
    else:
        chosen_night = None
        st.caption("No nights with sleep to inspect.")

# ---------------------------------------------------------------- the flow at a glance
after_clean = sum(len(v) for v in R.cleaned.values())
usable = int(nights["usable_sleep"].sum()) if not nights.empty else 0
flow = [
    ("Records in file", int(R.type_counts["records"].sum())),
    # Only the records inside "How far back", so the next step's drop is cleaning and nothing else.
    ("Layer 1 records in range", len(R.records)),
    ("After cleaning", after_clean),
    ("Sleep sessions", len(R.sessions)),
    ("Nights", len(nights)),
    ("Usable nights", usable),
    ("ML rows", len(ml)),
]
cols = st.columns(len(flow))
for col, (label, value) in zip(cols, flow):
    col.metric(label, f"{value:,}")

tabs = st.tabs(
    [
        "1 · Load",
        "2 · Clean",
        "3 · Sleep window",
        "4 · Nightly metrics",
        "5 · Missing data",
        "6 · Baselines & z-scores",
        "7 · ML-ready table",
        "8 · Daily updates",
    ]
)

# ======================================================================= 1. Load

data = AppData(R, nights, ml, main_sessions, chosen_night)
with tabs[0]:
    tab_load.render(data)
with tabs[1]:
    tab_clean.render(data)
with tabs[2]:
    tab_sleep.render(data)
with tabs[3]:
    tab_metrics.render(data)
with tabs[4]:
    tab_quality.render(data)
with tabs[5]:
    tab_baselines.render(data)
with tabs[6]:
    tab_ml_table.render(data)
with tabs[7]:
    tab_daily.render(data)
