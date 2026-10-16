"""
Step 3. Sleep window: resolve overlapping pieces, group them into sessions,
and pick each night's main sleep.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pandas as pd

from layer1 import config as C


def resolve_overlaps(stages: pd.DataFrame) -> pd.DataFrame:
    """
    Make sure no two sleep pieces cover the same moment, so minutes are never counted twice.

    Where pieces overlap, the moment goes to the stage with the lowest SLEEP_STAGE_PRIORITY
    (deep, REM and core beat asleep_unspecified, which beats awake). Between equal stages the
    piece that started first wins. Pieces are trimmed or split to the parts they win.
    Data without overlaps is returned unchanged.
    """
    if len(stages) < 2:
        return stages
    st = stages.sort_values(["start_utc", "end_utc"], kind="stable").reset_index(drop=True)
    starts, ends = st["start_utc"].tolist(), st["end_utc"].tolist()
    latest, overlap = ends[0], False
    for s, e in zip(starts[1:], ends[1:]):
        if s < latest:
            overlap = True
            break
        latest = max(latest, e)
    if not overlap:
        return stages

    rank = [C.SLEEP_STAGE_PRIORITY.get(s, len(C.SLEEP_STAGE_PRIORITY)) for s in st["stage"]]
    bounds = sorted(set(starts) | set(ends))
    pieces: list[tuple[int, Any, Any]] = []  # (row index, start, end) of the parts each piece keeps
    active, nxt = [], 0  # pieces covering the current stretch, next piece to start
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        while nxt < len(st) and starts[nxt] <= lo:
            active.append(nxt)
            nxt += 1
        active = [i for i in active if ends[i] > lo]
        live = [i for i in active if starts[i] <= lo and ends[i] >= hi]
        if not live:
            continue
        # Sorted by start already, so min() picks the earliest piece among equal stages.
        win = min(live, key=lambda i: (rank[i], starts[i], i))
        if pieces and pieces[-1][0] == win and pieces[-1][2] == lo:
            pieces[-1] = (win, pieces[-1][1], hi)
        else:
            pieces.append((win, lo, hi))

    # A trimmed piece's new start or end is always where another piece starts or ends, and that
    # piece recorded the local time there. Using it stays right even across a clock change.
    local_at: dict = {}
    for side in ("start", "end"):
        for moment, local in zip(st[f"{side}_utc"], st[f"{side}_local"]):
            local_at.setdefault(moment, local)

    rows = []
    for i, s, e in pieces:
        r = st.iloc[i].copy()
        if s != r["start_utc"]:
            r["start_local"] = local_at[s]
        if e != r["end_utc"]:
            r["end_local"] = local_at[e]
        r["start_utc"], r["end_utc"] = s, e
        rows.append(r)
    out = pd.DataFrame(rows, columns=st.columns).reset_index(drop=True)
    return out.astype(st.dtypes.to_dict())


def find_sleep_windows(stages: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Step 3. Group sleep pieces into sessions and choose each night's main sleep.

    A new session starts when the gap since the previous piece reaches SESSION_GAP_MIN.
    Each session's window runs from the first asleep piece (onset) to the last asleep
    piece (final awakening); awake pieces before onset or after final awakening are ignored.

    Overlapping pieces are resolved first (resolve_overlaps), so each minute has one stage.

    Returns
      sessions  one row per session, with night_date and is_main
      stages    the input stages (overlaps resolved) with a session_id column
    """
    st = resolve_overlaps(stages).sort_values("start_utc").reset_index(drop=True).copy()
    if st.empty:
        st["session_id"] = pd.Series(dtype=int)
        return pd.DataFrame(
            columns=[
                "session_id",
                "night_date",
                "onset_utc",
                "wake_utc",
                "onset_local",
                "wake_local",
                "asleep_min",
                "is_main",
            ]
        ), st

    gap = pd.Timedelta(minutes=C.SESSION_GAP_MIN)
    session_ids, current, latest_end = [], 0, None
    for start, end in zip(st["start_utc"], st["end_utc"]):
        if latest_end is not None and start - latest_end >= gap:
            current += 1
        session_ids.append(current)
        latest_end = end if latest_end is None else max(latest_end, end)
    st["session_id"] = session_ids

    rows = []
    for sid, g in st.groupby("session_id"):
        asleep = g[g["stage"].isin(C.ASLEEP_STAGES)]
        if asleep.empty:  # a session of only "awake" pieces is not sleep
            continue
        first, last = asleep.loc[asleep["start_utc"].idxmin()], asleep.loc[asleep["end_utc"].idxmax()]
        asleep_min = (asleep["end_utc"] - asleep["start_utc"]).dt.total_seconds().sum() / 60
        night = (first["start_local"] - timedelta(hours=C.NIGHT_SHIFT_HOURS)).date()
        rows.append(
            {
                "session_id": sid,
                "night_date": night,
                "onset_utc": first["start_utc"],
                "wake_utc": last["end_utc"],
                "onset_local": first["start_local"],
                "wake_local": last["end_local"],
                "asleep_min": asleep_min,
            }
        )
    sessions = pd.DataFrame(rows)
    sessions["is_main"] = False
    main_idx = sessions.groupby("night_date")["asleep_min"].idxmax()
    sessions.loc[main_idx, "is_main"] = True
    return sessions, st
