"""
Layer 1 preprocessing test platform.

    streamlit run app.py

Pick a sample file or upload an Apple Health export, then walk through the
tabs to see what each preprocessing step does. The last tab is the ML-ready table.
"""
import io
import os
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent))
import config as C  # noqa: E402
import incremental as I  # noqa: E402
import pipeline as P  # noqa: E402

HERE = Path(__file__).parent
SAMPLES = {
    "Alex: hard training block at the end": ("mock_export_alex_overreach.zip", "alex"),
    "Sam: steady and well recovered": ("mock_export_sam_steady.zip", "sam"),
    "Jordan: messy real-world data": ("mock_export_jordan_messy.zip", "jordan"),
}

# ---------------------------------------------------------------- chart styling
# Reference data-viz palette: sequential blue for sleep depth, categorical orange for
# highlights, status colors (always with a text label) for data quality.
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, BLUE_DARK, ORANGE = "#2a78d6", "#184f95", "#eb6834"
STAGE_COLORS = {"deep": "#104281", "core": "#3987e5", "rem": "#86b6ef",
                "asleep_unspecified": "#898781", "awake": ORANGE}
STAGE_LABELS = {"deep": "Deep", "core": "Core", "rem": "REM", "asleep_unspecified": "Asleep (no stage)",
                "awake": "Awake"}
GOOD, WARNING, NO_DATA = "#0ca30c", "#fab219", "#d3d1c7"
DIVERGE_NEG, DIVERGE_POS = "#2a78d6", "#e34948"


def style(fig: go.Figure, height: int = 320, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=36, b=8), template="plotly_white",
        font=dict(family='system-ui, -apple-system, "Segoe UI", sans-serif', size=13, color=INK2),
        paper_bgcolor="#fcfcfb", plot_bgcolor="#fcfcfb", hovermode="closest", showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None),
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False)
    return fig


def fmt_min(m) -> str:
    if m is None or pd.isna(m):
        return "–"
    return f"{int(m // 60)}h {int(round(m % 60)):02d}m"


def settings(*names):
    rows = [{"setting": n, "value": str(getattr(C, n))} for n in names]
    with st.expander("Settings used in this step (change them in config.py)"):
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


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
    mode = st.radio("Data source", ["Sample file", "Upload an export", "File path on this computer"],
                    help="Exports over ~200 MB are faster to load with the file path option.")
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
    days_choice = st.selectbox("How far back", ["30 days", "60 days", "90 days", "180 days", "1 year", "Everything"],
                               index=2, help="Counted back from the newest record in the file.")
    days = {"30 days": 30, "60 days": 60, "90 days": 90, "180 days": 180, "1 year": 365}.get(days_choice)

st.title("Layer 1 preprocessing")
st.caption("Apple Health export → cleaned data → nightly metrics → personal baselines → one ML-ready row per night. "
           "Nothing is trained here.")

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
        chosen_night = st.selectbox("Night of", night_options, index=default_idx,
                                    format_func=lambda d: pd.Timestamp(d).strftime("%a %b %d, %Y"),
                                    help="Used by the Sleep window and Nightly metrics tabs.")
    else:
        chosen_night = None
        st.caption("No nights with sleep to inspect.")

# ---------------------------------------------------------------- the flow at a glance
kept_types = R.type_counts.loc[R.type_counts["kept"], "records"].sum()
after_clean = sum(len(v) for v in R.cleaned.values())
usable = int(nights["usable_sleep"].sum()) if not nights.empty else 0
flow = [
    ("Records in file", int(R.type_counts["records"].sum())),
    ("Layer 1 records", int(kept_types)),
    ("After cleaning", after_clean),
    ("Sleep sessions", len(R.sessions)),
    ("Nights", len(nights)),
    ("Usable nights", usable),
    ("ML rows", len(ml)),
]
cols = st.columns(len(flow))
for col, (label, value) in zip(cols, flow):
    col.metric(label, f"{value:,}")

tabs = st.tabs(["1 · Load", "2 · Clean", "3 · Sleep window", "4 · Nightly metrics",
                "5 · Missing data", "6 · Baselines & z-scores", "7 · ML-ready table", "8 · Daily updates"])

# ======================================================================= 1. Load
with tabs[0]:
    st.subheader("Load the export")
    st.markdown("The export holds every type of Health data. Layer 1 only needs **heart rate, Apple's resting "
                "heart rate, HRV (SDNN) and sleep**, so everything else is skipped while reading. "
                "Each record keeps its UTC time (for ordering and durations) and its local clock time "
                "(to decide which night it belongs to).")
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
        st.dataframe(kept.groupby(["data", "source"]).size().rename("records").reset_index(),
                     hide_index=True, use_container_width=True)
    with st.expander("First 200 raw records"):
        st.dataframe(R.records.head(200)[["metric", "stage", "value", "unit", "source", "start_local", "end_local"]],
                     hide_index=True, use_container_width=True)
    settings("DEFAULT_DAYS")

# ======================================================================= 2. Clean
with tabs[1]:
    st.subheader("Clean")
    st.markdown("Four rules, applied in order:\n"
                "1. **Apple Watch only.** Other apps (chest-strap apps, third-party sleep trackers) measure "
                "differently, so mixing them would add noise. iPhone **In Bed** times are kept; they're used for time in bed.\n"
                "2. **Exact duplicates** removed (sync glitches, re-imports).\n"
                "3. **Impossible values** removed, such as a heart rate of 12 or 250 from a loose strap.\n"
                "4. **Broken sleep pieces** removed: shorter than 30 seconds or longer than 16 hours.\n\n"
                "Apple Watch doesn't share raw motion or sensor signals, so there is no motion-artifact filtering "
                "to do here: HealthKit values are already processed by the watch.")
    if R.removal_log.empty:
        st.success("Nothing needed removing in this file.")
    else:
        st.markdown("**What was removed and why**")
        st.dataframe(R.removal_log.rename(columns={"data": "data type", "removed": "records removed"}),
                     hide_index=True, use_container_width=True)

    before = R.records.assign(data=R.records["stage"].fillna(R.records["metric"])).groupby("data").size()
    after = pd.concat([v.assign(data=v["stage"].fillna(v["metric"])) for v in R.cleaned.values()]).groupby("data").size()
    ba = pd.DataFrame({"before": before, "after": after}).fillna(0).astype(int)
    ba["removed"] = ba["before"] - ba["after"]
    st.markdown("**Before and after**")
    st.dataframe(ba.reset_index().rename(columns={"index": "data", "data": "data"}), hide_index=True,
                 use_container_width=True)

    hr_removed = R.removed_rows[R.removed_rows["metric"] == "heart_rate"]
    hr_kept = R.cleaned["heart_rate"]
    if len(hr_kept):
        shown = hr_kept.sample(min(len(hr_kept), 15000), random_state=0).sort_values("start_local")
        fig = go.Figure()
        fig.add_trace(go.Scattergl(x=shown["start_local"], y=shown["value"], mode="markers", name="Kept",
                                   marker=dict(size=4, color=BLUE, opacity=0.35),
                                   hovertemplate="%{x|%b %d %H:%M}<br>%{y:.0f} bpm<extra>Kept</extra>"))
        for reason, color, symbol in (("Value outside plausible range", "#d03b3b", "x"),
                                      ("Not recorded by the Apple Watch", ORANGE, "diamond"),
                                      ("Exact duplicate", INK2, "circle-open")):
            part = hr_removed[hr_removed["reason"] == reason]
            if len(part):
                fig.add_trace(go.Scattergl(x=part["start_local"], y=part["value"], mode="markers",
                                           name=f"Removed: {reason.lower()} ({len(part)})",
                                           marker=dict(size=9, color=color, symbol=symbol, line=dict(width=1.5, color=color)),
                                           hovertemplate="%{x|%b %d %H:%M}<br>%{y:.0f} bpm<extra>" + reason + "</extra>"))
        lo, hi = C.VALID_RANGES["heart_rate"]
        for y in (lo, hi):
            fig.add_hline(y=y, line=dict(color=MUTED, dash="dot", width=1),
                          annotation_text=f"limit {y} bpm", annotation_position="top left",
                          annotation_font_color=MUTED)
        fig.update_yaxes(title="bpm")
        st.markdown("**Heart rate: kept vs removed**")
        st.plotly_chart(style(fig, 380), use_container_width=True)
        if len(hr_kept) > 15000:
            st.caption(f"Showing a random 15,000 of {len(hr_kept):,} kept readings; every removed reading is shown.")
    if len(R.removed_rows):
        with st.expander("Every removed record"):
            st.dataframe(R.removed_rows[["reason", "metric", "stage", "value", "source", "start_local", "end_local"]],
                         hide_index=True, use_container_width=True)
    settings("WATCH_SOURCE_KEYWORDS", "IN_BED_ANY_SOURCE", "VALID_RANGES", "MIN_SLEEP_SEGMENT_SEC",
             "MAX_SLEEP_SEGMENT_HOURS")

# ======================================================================= 3. Sleep window
with tabs[2]:
    st.subheader("Find the main sleep window")
    st.markdown(f"Sleep arrives as many short pieces (core, deep, REM, awake). Pieces less than "
                f"**{C.SESSION_GAP_MIN} minutes** apart are joined into one **session**. Each session's window runs "
                f"from **sleep onset** (first asleep piece) to **final awakening** (last asleep piece); awake time "
                f"before onset or after final awakening doesn't count. The **longest session** of each night is the "
                f"main sleep; any others are **naps** and are ignored. A night is named after the evening it starts.")
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
                xs += [s_, e_, None]; ys += [levels[stage]] * 2 + [None]
                text += [f"{STAGE_LABELS[stage]}: {mins:.0f} min"] * 2 + [None]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name=STAGE_LABELS[stage],
                                     line=dict(color=STAGE_COLORS[stage], width=14),
                                     hovertext=text, hoverinfo="text+x"))
        if len(ib):
            xs, ys = [], []
            for s_, e_ in zip(ib["start_local"], ib["end_local"]):
                xs += [s_, e_, None]; ys += [5, 5, None]
            fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name="In bed (iPhone)",
                                     line=dict(color=MUTED, width=8), hoverinfo="x+name"))
        has_ib = len(ib) > 0
        fig.add_vrect(x0=main["onset_local"], x1=main["wake_local"], fillcolor=BLUE, opacity=0.07, line_width=0)
        for x, lbl, anchor, shift in ((main["onset_local"], "Sleep onset", "left", 6),
                                      (main["wake_local"], "Final awakening", "right", -6)):
            fig.add_vline(x=x, line=dict(color=BLUE_DARK, width=1.5, dash="dash"))
            fig.add_annotation(x=x, y=5.65 if has_ib else 4.75, text=f"{lbl} {x:%H:%M}", showarrow=False, xanchor=anchor, xshift=shift,
                               font=dict(color=BLUE_DARK, size=12))
        for _, nap in night_sessions[~night_sessions["is_main"]].iterrows():
            fig.add_vrect(x0=nap["onset_local"], x1=nap["wake_local"], fillcolor=MUTED, opacity=0.12, line_width=0,
                          annotation_text="nap (ignored)", annotation_position="top left")
        fig.update_yaxes(tickvals=[1, 2, 3, 4, 5] if has_ib else [1, 2, 3, 4],
                         ticktext=["Deep", "Core", "REM", "Awake", "In bed"] if has_ib else ["Deep", "Core", "REM", "Awake"],
                         range=[0.4, 6.1] if has_ib else [0.4, 5.1], showgrid=False)
        x0 = min([main["onset_local"]] + list(ib["start_local"]) + list(night_sessions["onset_local"])) - pd.Timedelta(minutes=30)
        x1 = max([main["wake_local"]] + list(ib["end_local"]) + list(night_sessions["wake_local"])) + pd.Timedelta(minutes=30)
        fig.update_xaxes(tickformat="%H:%M", range=[x0, x1])
        st.plotly_chart(style(fig, 360), use_container_width=True)
        st.caption("Shaded area = the detected sleep window used for every metric in the next step.")

        sess = night_sessions.assign(
            role=np.where(night_sessions["is_main"], "main sleep", "nap"),
            start=night_sessions["onset_local"].dt.strftime("%a %H:%M"),
            end=night_sessions["wake_local"].dt.strftime("%a %H:%M"),
            asleep=night_sessions["asleep_min"].map(fmt_min))
        st.dataframe(sess[["role", "start", "end", "asleep"]], hide_index=True, use_container_width=True)
    with st.expander("All sessions"):
        if not R.sessions.empty:
            st.dataframe(R.sessions.assign(asleep=R.sessions["asleep_min"].map(fmt_min))[
                ["night_date", "is_main", "onset_local", "wake_local", "asleep"]], hide_index=True,
                use_container_width=True)
    settings("SESSION_GAP_MIN", "NIGHT_SHIFT_HOURS", "IN_BED_MATCH_HOURS")

# ======================================================================= 4. Nightly metrics
with tabs[3]:
    st.subheader("Nightly metrics")
    st.markdown(
        "- **Total sleep time (TST)** = core + deep + REM minutes inside the window.\n"
        "- **Time in bed** = iPhone *In Bed* when it exists, otherwise onset to final awakening.\n"
        "- **Sleep efficiency** = TST ÷ time in bed × 100.\n"
        f"- **Fragmentation** = awakenings per hour of sleep (an awakening is ≥ {C.MIN_AWAKENING_MIN:g} min awake). "
        "This replaces *awake minutes ÷ time in bed*, which is just 100 − efficiency when there's no In Bed data.\n"
        "- **Overnight HRV** = mean of the SDNN readings inside the window (the watch takes only a few per night).\n"
        f"- **Overnight resting HR** = lowest {C.RHR_WINDOW_MIN}-minute average heart rate during sleep. "
        "Apple's own resting HR is a whole-day value, so it's shown only for comparison.")
    if chosen_night is not None:
        row = nights[nights["night_date"] == chosen_night].iloc[0]
        st.markdown(f"#### Night of {pd.Timestamp(chosen_night).strftime('%A %b %d')}")
        m = st.columns(6)
        m[0].metric("Total sleep", fmt_min(row["tst_min"]))
        m[1].metric("Efficiency", f"{row['sleep_efficiency_pct']:.1f}%", help=f"Time in bed from: {row['tib_source']}")
        m[2].metric("Awakenings", f"{int(row['awakenings'])}", help=f"{row['fragmentation_per_hr']:.2f} per hour of sleep")
        m[3].metric("Awake after onset", fmt_min(row["waso_min"]))
        m[4].metric("Overnight HRV", "–" if pd.isna(row["hrv_night_ms"]) else f"{row['hrv_night_ms']:.1f} ms",
                    help=f"{int(row['hrv_count'])} reading(s) that night")
        m[5].metric("Overnight resting HR", "–" if pd.isna(row["rhr_night_bpm"]) else f"{row['rhr_night_bpm']:.1f} bpm",
                    help=f"Apple's daily value: {row['apple_rhr_bpm']:.0f} bpm" if pd.notna(row["apple_rhr_bpm"]) else None)

        main = main_sessions[main_sessions["night_date"] == chosen_night].iloc[0]
        lo, hi = main["onset_utc"], main["wake_utc"]
        rhr = P.overnight_rhr(R.cleaned["heart_rate"], lo, hi)
        hr = R.cleaned["heart_rate"]
        pad = pd.Timedelta(minutes=45)
        around = hr[(hr["start_utc"] >= lo - pad) & (hr["start_utc"] <= hi + pad)]
        offset = main["onset_local"] - main["onset_utc"].tz_localize(None)  # UTC -> local for this night
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=around["start_local"], y=around["value"], mode="markers", name="Heart rate readings",
                                 marker=dict(size=6, color=BLUE, opacity=0.45),
                                 hovertemplate="%{x|%H:%M}<br>%{y:.0f} bpm<extra></extra>"))
        if rhr["rolling"] is not None:
            roll = rhr["rolling"]
            full = roll.index - pd.Timedelta(minutes=C.RHR_WINDOW_MIN) >= lo
            r_ok = roll[full]
            fig.add_trace(go.Scatter(x=r_ok.index.tz_localize(None) + offset, y=r_ok["mean"], mode="lines",
                                     name=f"{C.RHR_WINDOW_MIN}-min rolling average", line=dict(color=BLUE_DARK, width=2),
                                     hovertemplate="%{x|%H:%M}<br>%{y:.1f} bpm<extra>rolling avg</extra>"))
        if pd.notna(rhr["rhr_window_end_utc"]):
            end_local = rhr["rhr_window_end_utc"].tz_localize(None) + offset
            fig.add_vrect(x0=end_local - pd.Timedelta(minutes=C.RHR_WINDOW_MIN), x1=end_local,
                          fillcolor=ORANGE, opacity=0.18, line_width=0)
            fig.add_annotation(x=end_local - pd.Timedelta(minutes=C.RHR_WINDOW_MIN / 2), y=rhr["rhr_night_bpm"],
                               text=f"Lowest {C.RHR_WINDOW_MIN}-min average: {rhr['rhr_night_bpm']:.1f} bpm",
                               showarrow=True, arrowhead=0, ay=-40, font=dict(color=INK, size=12),
                               bgcolor="#fcfcfb")
        fig.add_vrect(x0=main["onset_local"], x1=main["wake_local"], fillcolor=BLUE, opacity=0.05, line_width=0)
        fig.update_xaxes(tickformat="%H:%M")
        fig.update_yaxes(title="bpm")
        st.markdown("**Overnight heart rate** (shaded blue = sleep window, orange = lowest 30-minute stretch)")
        st.plotly_chart(style(fig, 340), use_container_width=True)

        hrv = R.cleaned["hrv_sdnn"]
        night_hrv = hrv[(hrv["start_utc"] >= lo) & (hrv["start_utc"] <= hi)]
        if len(night_hrv):
            st.markdown("**HRV readings used tonight**")
            st.dataframe(pd.DataFrame({"time": night_hrv["start_local"].dt.strftime("%H:%M"),
                                       "SDNN (ms)": night_hrv["value"].round(1)}), hide_index=True)
        else:
            st.warning("No HRV reading inside tonight's sleep window, so HRV is missing for this night.")

    st.markdown("#### Every night")
    has = nights[nights["tst_min"].notna()]
    fig = go.Figure()
    for stage, col in (("deep", "deep_min"), ("core", "core_min"), ("rem", "rem_min"),
                       ("asleep_unspecified", "unspecified_min")):
        if has[col].fillna(0).sum() == 0:
            continue
        fig.add_trace(go.Bar(x=pd.to_datetime(has["night_date"]), y=has[col] / 60, name=STAGE_LABELS[stage],
                             marker=dict(color=STAGE_COLORS[stage], line=dict(color="#fcfcfb", width=1)),
                             hovertemplate="%{x|%b %d}<br>%{y:.1f} h<extra>" + STAGE_LABELS[stage] + "</extra>"))
    fig.update_layout(barmode="stack", bargap=0.25)
    st.markdown("**Total sleep time by stage**")
    fig.update_yaxes(title="hours")
    st.plotly_chart(style(fig, 320), use_container_width=True)
    show = nights[["night_date", "tst_min", "deep_min", "rem_min", "waso_min", "awakenings", "tib_min", "tib_source",
                   "sleep_efficiency_pct", "fragmentation_per_hr", "hrv_night_ms", "hrv_count", "rhr_night_bpm",
                   "apple_rhr_bpm"]].copy()
    st.dataframe(show.round(2), hide_index=True, use_container_width=True)
    settings("MIN_AWAKENING_MIN", "RHR_WINDOW_MIN", "RHR_MIN_SAMPLES_IN_WINDOW", "HRV_LOG_TRANSFORM")

# ======================================================================= 5. Missing data
with tabs[4]:
    st.subheader("Missing data and quality flags")
    st.markdown(
        "Every calendar night gets a row, even nights with nothing recorded, so gaps are visible instead of silently "
        "skipped. Each value is then marked **usable** or not. Only usable values go into the personal baselines.\n"
        f"- **Sleep** is usable if the watch recorded at least {C.MIN_TST_FOR_USABLE_MIN / 60:g} hours.\n"
        "- **HRV** needs usable sleep plus at least one HRV reading in the window.\n"
        f"- **Overnight resting HR** needs usable sleep plus at least {C.MIN_HR_SAMPLES_PER_SLEEP_HOUR} heart rate "
        "readings per hour of sleep.")
    if not nights.empty:
        c = st.columns(4)
        c[0].metric("Calendar nights", len(nights))
        c[1].metric("Usable sleep", int(nights["usable_sleep"].sum()))
        c[2].metric("Usable HRV", int(nights["usable_hrv"].sum()))
        c[3].metric("Usable resting HR", int(nights["usable_rhr"].sum()))

        checks = [("Overnight resting HR", "usable_rhr"), ("HRV", "usable_hrv"), ("Sleep", "usable_sleep")]
        z, text = [], []
        for label, col in checks:
            row_z, row_t = [], []
            for _, r in nights.iterrows():
                if r["flag_no_sleep_data"]:
                    row_z.append(0); row_t.append("No data")
                elif r[col]:
                    row_z.append(2); row_t.append("Usable")
                else:
                    row_z.append(1); row_t.append("Flagged: " + (r["quality_notes"] or "not usable"))
            z.append(row_z); text.append(row_t)
        x = pd.to_datetime(nights["night_date"])
        fig = go.Figure(go.Heatmap(
            z=z, x=x, y=[c[0] for c in checks], text=text, xgap=2, ygap=2,
            colorscale=[[0, NO_DATA], [0.33, NO_DATA], [0.34, WARNING], [0.66, WARNING], [0.67, GOOD], [1, GOOD]],
            zmin=0, zmax=2, showscale=False,
            hovertemplate="%{x|%a %b %d}<br>%{y}: %{text}<extra></extra>"))
        st.markdown("**Each night's data:** 🟩 usable · 🟨 flagged · ⬜ no data (hover a square for the reason)")
        fig.update_xaxes(showgrid=False, tickformat="%b %d")
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(style(fig, 230, legend=False), use_container_width=True)

        flagged = nights[nights["quality_notes"] != ""][["night_date", "quality_notes", "tst_min", "hrv_count",
                                                          "hr_night_count"]]
        if len(flagged):
            st.markdown("**Flagged nights**")
            st.dataframe(flagged.assign(tst_min=flagged["tst_min"].map(fmt_min)), hide_index=True,
                         use_container_width=True)
        else:
            st.success("Every night is complete.")
    settings("MIN_TST_FOR_USABLE_MIN", "MIN_HR_SAMPLES_PER_SLEEP_HOUR")

# ======================================================================= 6. Baselines
with tabs[5]:
    st.subheader("Personal baselines and z-scores")
    st.markdown(
        f"Each night is compared with **the same person's previous {C.BASELINE_WINDOW_NIGHTS} nights** "
        f"(tonight is never part of its own baseline), using only usable values. A z-score appears once the "
        f"baseline has **{C.BASELINE_MIN_NIGHTS} nights**.\n\n"
        "**z = (tonight − baseline mean) ÷ baseline SD.** 0 means a typical night for this person; −2 means well below "
        "their usual. HRV is log-transformed first because its values are skewed. Signs are left as they are: for "
        "resting HR and fragmentation, a high z is the *bad* direction.")
    if not nights.empty:
        label_to_col = {v[1]: k for k, v in C.ZSCORE_METRICS.items()}
        pick = st.selectbox("Metric", list(label_to_col))
        col = label_to_col[pick]
        zcol, _, gate = C.ZSCORE_METRICS[col]
        x = pd.to_datetime(nights["night_date"])
        val = nights[col].where(nights[gate].fillna(False).astype(bool))
        mu, sd = nights[f"{col}_base_mean"], nights[f"{col}_base_sd"]
        unit = {"hrv_ln": "ln(ms)", "rhr_night_bpm": "bpm", "tst_min": "minutes",
                "sleep_efficiency_pct": "%", "fragmentation_per_hr": "per hour"}[col]

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.62, 0.38], vertical_spacing=0.08)
        fig.add_trace(go.Scatter(x=x, y=mu + sd, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip"),
                      row=1, col=1)
        fig.add_trace(go.Scatter(x=x, y=mu - sd, mode="lines", line=dict(width=0), fill="tonexty",
                                 fillcolor="rgba(137,135,129,0.18)", name="Baseline ± 1 SD", hoverinfo="skip"),
                      row=1, col=1)
        fig.add_trace(go.Scatter(x=x, y=mu, mode="lines", name="Baseline mean",
                                 line=dict(color=MUTED, width=2, dash="dash"),
                                 hovertemplate="%{x|%b %d}<br>baseline %{y:.2f}<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(x=x, y=val, mode="lines+markers", name="Tonight",
                                 line=dict(color=BLUE, width=2), marker=dict(size=8, color=BLUE,
                                                                             line=dict(color="#fcfcfb", width=2)),
                                 connectgaps=False,
                                 hovertemplate="%{x|%b %d}<br>%{y:.2f} " + unit + "<extra></extra>"), row=1, col=1)
        zs = nights[zcol]
        fig.add_trace(go.Bar(x=x, y=zs, name="z-score", showlegend=False,
                             marker_color=np.where(zs < 0, DIVERGE_NEG, DIVERGE_POS),
                             hovertemplate="%{x|%b %d}<br>z = %{y:.2f}<extra></extra>"), row=2, col=1)
        for y in (-2, 2):
            fig.add_hline(y=y, line=dict(color=MUTED, dash="dot", width=1), row=2, col=1)
        fig.update_yaxes(title_text=unit, row=1, col=1)
        fig.update_yaxes(title_text="z", row=2, col=1)
        fig.update_xaxes(tickformat="%b %d")
        st.markdown(f"**{pick}: tonight vs personal baseline** (top) **and z-score** (bottom; dotted lines at ±2)")
        st.plotly_chart(style(fig, 480), use_container_width=True)
        first_z = nights.loc[zs.notna(), "night_date"].min()
        st.caption("Gaps = nights where this value isn't usable. "
                   + (f"First z-score on {pd.Timestamp(first_z):%b %d}; earlier nights are still building the baseline."
                      if pd.notna(first_z) else "Not enough usable nights yet for any z-score."))
        table = pd.DataFrame({"night": nights["night_date"], "value": val.round(3),
                              "baseline nights": nights[f"{col}_base_n"], "baseline mean": mu.round(3),
                              "baseline SD": sd.round(3), "z": zs.round(2)})
        st.dataframe(table, hide_index=True, use_container_width=True)
    settings("BASELINE_WINDOW_NIGHTS", "BASELINE_MIN_NIGHTS", "MIN_SD_FRACTION_OF_MEAN")

# ======================================================================= 7. ML table
with tabs[6]:
    st.subheader("ML-ready table")
    st.markdown("One row per night for this person, in a fixed column order. Nights with missing data stay in the "
                "table with their flags, so the model step can decide how to handle them. "
                "`readiness_label` is an **empty placeholder** for the training label you'll collect later.")
    c = st.columns(4)
    c[0].metric("Rows (nights)", len(ml))
    c[1].metric("Columns", ml.shape[1])
    c[2].metric("Rows with z-scores", int(ml[["z_hrv", "z_rhr", "z_tst"]].notna().any(axis=1).sum()) if len(ml) else 0)
    c[3].metric("Fully usable rows", int((ml["usable_sleep"] & ml["usable_hrv"] & ml["usable_rhr"]).sum()) if len(ml) else 0)
    st.dataframe(ml, hide_index=True, use_container_width=True, height=420)
    safe = "".join(ch for ch in R.person_id if ch.isalnum() or ch in "-_") or "tester"
    st.download_button("Download ML-ready CSV", ml.to_csv(index=False).encode("utf-8"),
                       file_name=f"layer1_features_{safe}.csv", mime="text/csv", type="primary")
    with st.expander("What every column means"):
        st.dataframe(P.column_dictionary(), hide_index=True, use_container_width=True)
    with st.expander("Everything computed (all intermediate columns)"):
        st.dataframe(nights, hide_index=True, use_container_width=True)
        st.download_button("Download full nightly table", nights.to_csv(index=False).encode("utf-8"),
                           file_name=f"layer1_full_{safe}.csv", mime="text/csv")

# ======================================================================= 8. Daily updates
with tabs[7]:
    st.subheader("Daily updates: only process what's new")
    st.markdown(
        "In the real system the first sync sends the whole history; after that each sync brings about one day. "
        "This tab replays the selected file **one daily sync at a time**, the way the phone would send it, and "
        "processes only what each sync needs:\n"
        f"1. **A night is processed at the user's update time the next day** ({C.DEFAULT_UPDATE_TIME[0]}:"
        f"{C.DEFAULT_UPDATE_TIME[1]:02d} by default), or earlier if they tap **Update now** after waking.\n"
        "2. **Every run processes the new night and redoes the nights just before it**, to pick up data that synced late.\n"
        "3. **Skipped days are caught up**: every ready night that hasn't been processed yet is processed.\n\n"
        f"Baselines for the new nights come from the **saved nightly rows** of earlier nights, so old raw data is "
        f"never re-read. Each simulated sync happens at {C.SIM_SYNC_HOUR}:00.")

    recs_all = R.records
    asleep = recs_all[recs_all["stage"].isin(C.ASLEEP_STAGES)]
    if asleep.empty:
        st.info("This file has no sleep data, so there's nothing to process night by night.")
    else:
        first_day = recs_all["start_local"].min().date()
        last_wake = asleep["end_local"].max()
        end_sync = datetime.combine(last_wake.date(), time(C.SIM_SYNC_HOUR))
        if end_sync < last_wake:
            end_sync += timedelta(days=1)
        total_days = max((end_sync.date() - first_day).days, 1)

        c1, c2, c3 = st.columns(3)
        initial_days = c1.number_input("Days in the first load", min_value=1, max_value=total_days,
                                       value=min(21, max(total_days - 7, 1)), step=1,
                                       help="The first sync sends this many days of history at once.")
        recompute_n = c2.selectbox("Recompute the last … nights each run", [1, 2, 3],
                                   index=[1, 2, 3].index(C.RECOMPUTE_NIGHTS) if C.RECOMPUTE_NIGHTS in (1, 2, 3) else 1,
                                   help="2 = the new night plus the night before it. 1 = never redo anything.")
        late_hrv = c3.checkbox("HRV syncs a day late", value=False,
                               help="Simulates HRV readings reaching the phone 26 hours after they're measured.")

        settings_now = (R.person_id, len(recs_all), str(recs_all["start_utc"].min()), int(initial_days),
                        int(recompute_n), bool(late_hrv))
        state = st.session_state.get("daily")

        def start_over():
            arrive = I.arrival_times(recs_all, late_hrv)
            first_sync = min(datetime.combine(first_day + timedelta(days=int(initial_days)), time(C.SIM_SYNC_HOUR)),
                             end_sync)
            proc = I.DailyProcessor(R.person_id, int(recompute_n))
            st.session_state["daily"] = {"settings": settings_now, "proc": proc, "arrive": arrive,
                                         "prev": None, "next": first_sync}
            run_sync(st.session_state["daily"])

        def run_sync(stt):
            sync = stt["next"]
            arrive = stt["arrive"]
            m = (arrive <= sync) if stt["prev"] is None else ((arrive > stt["prev"]) & (arrive <= sync))
            report = stt["proc"].sync(recs_all[m], sync)
            full = I.full_reprocessing(recs_all[arrive <= sync], R.person_id, report.ready_through) \
                if report.ready_through else pd.DataFrame()
            stt["check"] = I.compare(stt["proc"].ml_table, full)
            stt["prev"], stt["next"] = sync, sync + timedelta(days=1)

        if state is None or state["settings"] != settings_now:
            if state is not None:
                st.caption("Settings changed, so the simulation restarted from the first load.")
            start_over()
            state = st.session_state["daily"]

        remaining = (end_sync.date() - state["prev"].date()).days
        b1, b2, b3, _ = st.columns([1.2, 1.2, 1, 3])
        if b1.button("Add next day", type="primary", disabled=remaining < 1, use_container_width=True):
            run_sync(state)
            st.rerun()
        if b2.button("Skip ahead 3 days", disabled=remaining < 1, use_container_width=True,
                     help="The phone didn't sync for 3 days; the next sync has to catch up."):
            state["next"] = min(state["prev"] + timedelta(days=3), end_sync)
            run_sync(state)
            st.rerun()
        if b3.button("Start over", use_container_width=True):
            start_over()
            st.rerun()

        proc = state["proc"]
        rep = proc.reports[-1]
        ml_daily = proc.ml_table
        fmt_d = lambda d: pd.Timestamp(d).strftime("%a %b %d")
        st.markdown(f"**Data received up to {state['prev']:%a %b %d, %H:%M}** · "
                    f"{len(ml_daily)} nights processed · "
                    + (f"{remaining} more day(s) left in this file" if remaining > 0 else "end of this file reached"))

        st.markdown(f"#### Run {rep.run}: {rep.kind}")
        k = st.columns(4)
        k[0].metric("Records received", f"{sum(rep.received.values()):,}",
                    help=", ".join(f"{t}: {n:,}" for t, n in sorted(rep.received.items())) or "none")
        k[1].metric("New nights processed", len(rep.new_nights))
        k[2].metric("Nights redone", len(rep.recomputed_nights))
        k[3].metric("Saved raw records read", f"{rep.raw_rows_read:,}",
                    help=f"Out of {rep.raw_rows_saved:,} saved so far. Only the raw data around the nights "
                         "being processed is read.")
        lines = []
        if rep.new_nights:
            lines.append("**New:** " + ", ".join(fmt_d(d) for d in rep.new_nights))
        for d in rep.recomputed_nights:
            ch = rep.changed.get(d)
            lines.append(f"**Redone:** {fmt_d(d)} → " + (
                "updated " + ", ".join(f"`{c}`" for c in ch) + " (data that arrived late)" if ch else "no change"))
        if rep.duplicates_skipped:
            lines.append(f"{rep.duplicates_skipped:,} records were already saved and were skipped.")
        if rep.removed_by_cleaning:
            lines.append(f"{rep.removed_by_cleaning:,} records removed by cleaning.")
        if not rep.new_nights and not rep.recomputed_nights:
            lines.append("No night was ready yet, so nothing was processed.")
        st.markdown("  \n".join(lines))

        check = state.get("check", pd.DataFrame())
        if check is None or check.empty:
            st.success(f"✓ Identical to processing all received data at once: {len(ml_daily)} nights, "
                       "every column.")
        else:
            nights_off = sorted(set(check["night"]))
            st.warning(f"Differs from processing everything at once on {len(nights_off)} night(s): "
                       + ", ".join(fmt_d(n) for n in nights_off[:6])
                       + ". Usually this means data arrived after its night stopped being redone; try "
                         "recomputing 2 nights.")
            with st.expander("Differences"):
                st.dataframe(check, hide_index=True, use_container_width=True)

        # Which nights each run touched.
        all_nights = sorted({d for r in proc.reports for d in r.new_nights + r.recomputed_nights})
        if all_nights:
            st.markdown("**What each run processed** · 🟦 new night · 🟧 redone")
            idx = {d: i for i, d in enumerate(all_nights)}
            z = np.full((len(proc.reports), len(all_nights)), np.nan)
            text = [[""] * len(all_nights) for _ in proc.reports]
            for r_i, r in enumerate(proc.reports):
                for d in r.new_nights:
                    z[r_i, idx[d]] = 1; text[r_i][idx[d]] = "new"
                for d in r.recomputed_nights:
                    z[r_i, idx[d]] = 2
                    text[r_i][idx[d]] = "redone: " + (", ".join(r.changed[d]) if d in r.changed else "no change")
            ylab = [f"Run {r.run} · {r.sync_time:%b %d}" for r in proc.reports]
            fig = go.Figure(go.Heatmap(
                z=z, x=[pd.Timestamp(d) for d in all_nights], y=ylab, text=text, xgap=2, ygap=2,
                colorscale=[[0, BLUE], [0.5, BLUE], [0.5, ORANGE], [1, ORANGE]], zmin=1, zmax=2, showscale=False,
                hovertemplate="%{y}<br>Night of %{x|%a %b %d}: %{text}<extra></extra>"))
            fig.update_yaxes(autorange="reversed", showgrid=False)
            fig.update_xaxes(showgrid=False, tickformat="%b %d", title="Night")
            st.plotly_chart(style(fig, max(180, 26 * len(proc.reports) + 90), legend=False), use_container_width=True)

        st.markdown("**Saved ML-ready table** (rows touched by the last run are highlighted)")
        new_set = {str(d) for d in rep.new_nights}
        redo_set = {str(d) for d in rep.recomputed_nights}

        def shade(row):
            color = "#cde2fb" if row["night_date"] in new_set else ("#fbe1d5" if row["night_date"] in redo_set else "")
            return [f"background-color: {color}" if color else ""] * len(row)

        show_cols = ["night_date", "tst_min", "sleep_efficiency_pct", "fragmentation_per_hr", "hrv_night_ms",
                     "hrv_count", "rhr_night_bpm", "apple_rhr_bpm", "z_hrv", "z_rhr", "z_tst", "quality_notes"]
        view = ml_daily[show_cols].iloc[::-1].reset_index(drop=True)
        st.dataframe(view.style.apply(shade, axis=1).format(precision=2, na_rep="–"), hide_index=True,
                     use_container_width=True, height=360)
        safe_d = "".join(ch for ch in R.person_id if ch.isalnum() or ch in "-_") or "tester"
        st.download_button("Download this table as CSV", ml_daily.to_csv(index=False).encode("utf-8"),
                           file_name=f"layer1_features_{safe_d}_daily.csv", mime="text/csv")
    settings("DEFAULT_UPDATE_TIME", "RECOMPUTE_NIGHTS", "LATE_DATA_DAYS", "SIM_SYNC_HOUR")
