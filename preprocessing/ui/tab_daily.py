"""Tab 8: replay the file one sync at a time to show the daily updates."""

from datetime import datetime, time, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from layer1 import config as C
from layer1 import incremental as I
from ui.common import (
    BLUE,
    ORANGE,
    AppData,
    settings,
    style,
)


def render(data: AppData) -> None:
    R = data.R
    st.subheader("Daily updates: only process what's new")
    st.markdown(
        "In the real system the first sync sends the whole history; after that each sync brings about one day. "
        "This tab replays the selected file **one daily sync at a time**, the way the phone would send it, and "
        "processes only what each sync needs:\n"
        f"1. **A night is processed at the user's update time the next day** ({C.DEFAULT_UPDATE_TIME[0]}:"
        f"{C.DEFAULT_UPDATE_TIME[1]:02d} by default), or earlier if they tap **Update now** after waking.\n"
        "2. **Every run processes the new night and redoes the nights just before it**, "
        "to pick up data that synced late.\n"
        "3. **Skipped days are caught up**: every ready night that hasn't been processed yet is processed.\n\n"
        f"Baselines for the new nights come from the **saved nightly rows** of earlier nights, so old raw data is "
        f"never re-read. Each simulated sync happens at {C.SIM_SYNC_HOUR}:00."
    )

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
        initial_days = c1.number_input(
            "Days in the first load",
            min_value=1,
            max_value=total_days,
            value=min(21, max(total_days - 7, 1)),
            step=1,
            help="The first sync sends this many days of history at once.",
        )
        recompute_n = c2.selectbox(
            "Recompute the last … nights each run",
            [1, 2, 3],
            index=[1, 2, 3].index(C.RECOMPUTE_NIGHTS) if C.RECOMPUTE_NIGHTS in (1, 2, 3) else 1,
            help="2 = the new night plus the night before it. 1 = never redo anything.",
        )
        late_hrv = c3.checkbox(
            "HRV syncs a day late",
            value=False,
            help="Simulates HRV readings reaching the phone 26 hours after they're measured.",
        )

        settings_now = (
            R.person_id,
            len(recs_all),
            str(recs_all["start_utc"].min()),
            int(initial_days),
            int(recompute_n),
            bool(late_hrv),
        )
        state = st.session_state.get("daily")

        def start_over():
            arrive = I.arrival_times(recs_all, late_hrv)
            first_sync = min(
                datetime.combine(first_day + timedelta(days=int(initial_days)), time(C.SIM_SYNC_HOUR)), end_sync
            )
            proc = I.DailyProcessor(R.person_id, int(recompute_n))
            st.session_state["daily"] = {
                "settings": settings_now,
                "proc": proc,
                "arrive": arrive,
                "prev": None,
                "next": first_sync,
            }
            run_sync(st.session_state["daily"])

        def run_sync(stt):
            sync = stt["next"]
            arrive = stt["arrive"]
            reports = stt["proc"].reports
            # A click while the last run was still going interrupts it. If that run already got this
            # day in, don't sync the same day twice, just move on.
            if reports and reports[-1].sync_time == sync:
                report = reports[-1]
            else:
                m = (arrive <= sync) if stt["prev"] is None else ((arrive > stt["prev"]) & (arrive <= sync))
                report = stt["proc"].sync(recs_all[m], sync)
            full = (
                I.full_reprocessing(recs_all[arrive <= sync], R.person_id, report.ready_through)
                if report.ready_through
                else pd.DataFrame()
            )
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
        if b2.button(
            "Skip ahead 3 days",
            disabled=remaining < 1,
            use_container_width=True,
            help="The phone didn't sync for 3 days; the next sync has to catch up.",
        ):
            state["next"] = min(state["prev"] + timedelta(days=3), end_sync)
            run_sync(state)
            st.rerun()
        if b3.button("Start over", use_container_width=True):
            start_over()
            st.rerun()

        proc = state["proc"]
        rep = proc.reports[-1]
        ml_daily = proc.ml_table

        def fmt_d(d):
            return pd.Timestamp(d).strftime("%a %b %d")

        st.markdown(
            f"**Data received up to {state['prev']:%a %b %d, %H:%M}** · "
            f"{len(ml_daily)} nights processed · "
            + (f"{remaining} more day(s) left in this file" if remaining > 0 else "end of this file reached")
        )

        st.markdown(f"#### Run {rep.run}: {rep.kind}")
        k = st.columns(4)
        k[0].metric(
            "Records received",
            f"{sum(rep.received.values()):,}",
            help=", ".join(f"{t}: {n:,}" for t, n in sorted(rep.received.items())) or "none",
        )
        k[1].metric("New nights processed", len(rep.new_nights))
        k[2].metric("Nights redone", len(rep.recomputed_nights))
        k[3].metric(
            "Saved raw records read",
            f"{rep.raw_rows_read:,}",
            help=f"Out of {rep.raw_rows_saved:,} saved so far. Only the raw data around the nights "
            "being processed is read.",
        )
        lines = []
        if rep.new_nights:
            lines.append("**New:** " + ", ".join(fmt_d(d) for d in rep.new_nights))
        for d in rep.recomputed_nights:
            ch = rep.changed.get(d)
            lines.append(
                f"**Redone:** {fmt_d(d)} → "
                + ("updated " + ", ".join(f"`{c}`" for c in ch) + " (data that arrived late)" if ch else "no change")
            )
        if rep.duplicates_skipped:
            lines.append(f"{rep.duplicates_skipped:,} records were already saved and were skipped.")
        if rep.removed_by_cleaning:
            lines.append(f"{rep.removed_by_cleaning:,} records removed by cleaning.")
        if not rep.new_nights and not rep.recomputed_nights:
            lines.append("No night was ready yet, so nothing was processed.")
        st.markdown("  \n".join(lines))

        check = state.get("check", pd.DataFrame())
        if check is None or check.empty:
            st.success(f"✓ Identical to processing all received data at once: {len(ml_daily)} nights, every column.")
        else:
            nights_off = sorted(set(check["night"]))
            st.warning(
                f"Differs from processing everything at once on {len(nights_off)} night(s): "
                + ", ".join(fmt_d(n) for n in nights_off[:6])
                + ". Usually this means data arrived after its night stopped being redone; try "
                "recomputing 2 nights."
            )
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
                    z[r_i, idx[d]] = 1
                    text[r_i][idx[d]] = "new"
                for d in r.recomputed_nights:
                    z[r_i, idx[d]] = 2
                    text[r_i][idx[d]] = "redone: " + (", ".join(r.changed[d]) if d in r.changed else "no change")
            ylab = [f"Run {r.run} · {r.sync_time:%b %d}" for r in proc.reports]
            fig = go.Figure(
                go.Heatmap(
                    z=z,
                    x=[pd.Timestamp(d) for d in all_nights],
                    y=ylab,
                    text=text,
                    xgap=2,
                    ygap=2,
                    colorscale=[[0, BLUE], [0.5, BLUE], [0.5, ORANGE], [1, ORANGE]],
                    zmin=1,
                    zmax=2,
                    showscale=False,
                    hovertemplate="%{y}<br>Night of %{x|%a %b %d}: %{text}<extra></extra>",
                )
            )
            fig.update_yaxes(autorange="reversed", showgrid=False)
            fig.update_xaxes(showgrid=False, tickformat="%b %d", title="Night")
            st.plotly_chart(style(fig, max(180, 26 * len(proc.reports) + 90), legend=False), use_container_width=True)

        st.markdown("**Saved ML-ready table** (rows touched by the last run are highlighted)")
        new_set = {str(d) for d in rep.new_nights}
        redo_set = {str(d) for d in rep.recomputed_nights}

        def shade(row):
            color = "#cde2fb" if row["night_date"] in new_set else ("#fbe1d5" if row["night_date"] in redo_set else "")
            return [f"background-color: {color}" if color else ""] * len(row)

        show_cols = [
            "night_date",
            "tst_min",
            "sleep_efficiency_pct",
            "fragmentation_per_hr",
            "hrv_night_ms",
            "hrv_count",
            "rhr_night_bpm",
            "apple_rhr_bpm",
            "z_hrv",
            "z_rhr",
            "z_tst",
            "quality_notes",
        ]
        view = ml_daily[show_cols].iloc[::-1].reset_index(drop=True)
        st.dataframe(
            view.style.apply(shade, axis=1).format(precision=2, na_rep="–"),
            hide_index=True,
            use_container_width=True,
            height=360,
        )
        safe_d = "".join(ch for ch in R.person_id if ch.isalnum() or ch in "-_") or "tester"
        st.download_button(
            "Download this table as CSV",
            ml_daily.to_csv(index=False).encode("utf-8"),
            file_name=f"layer1_features_{safe_d}_daily.csv",
            mime="text/csv",
        )
    settings("DEFAULT_UPDATE_TIME", "RECOMPUTE_NIGHTS", "LATE_DATA_DAYS", "SIM_SYNC_HOUR")
