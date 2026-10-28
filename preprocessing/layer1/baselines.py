"""
Step 6. Baselines and z-scores: previous nights only, never tonight.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from layer1 import config as C


def add_baselines(nights: pd.DataFrame, only_dates=None) -> pd.DataFrame:
    """
    Step 6. For each night and each metric in ZSCORE_METRICS:
      baseline = values from the previous BASELINE_WINDOW_NIGHTS calendar nights (not tonight),
                 using only nights where that metric is usable
      z        = (tonight - baseline mean) / baseline SD, only if the baseline has
                 BASELINE_MIN_NIGHTS values and tonight's own value is usable

    only_dates: if given, only those nights are (re)computed and every other row keeps the
    baseline it already has. Daily updates use this so old nights aren't touched.
    """
    df = nights.copy()
    days = pd.to_datetime(df["night_date"]).to_numpy()
    targets = None if only_dates is None else set(only_dates)
    rows = range(len(df)) if targets is None else [i for i, d in enumerate(df["night_date"]) if d in targets]
    span = np.timedelta64(C.BASELINE_WINDOW_NIGHTS, "D")
    for col, (zcol, _label, gate) in C.ZSCORE_METRICS.items():
        usable = df[col].where(df[gate].fillna(False).astype(bool)).to_numpy()
        names = (f"{col}_base_mean", f"{col}_base_sd", f"{col}_base_n", zcol)
        # Work on plain arrays and write each column once, pandas row-by-row writes are slow.
        out = {n: df[n].to_numpy(dtype=float, copy=True) if n in df else np.full(len(df), np.nan) for n in names}
        for i in rows:
            d = days[i]
            vals = pd.Series(usable[(days >= d - span) & (days < d)]).dropna()
            n = len(vals)
            if n >= C.BASELINE_MIN_NIGHTS:
                mu = float(vals.mean())
                sd = max(float(vals.std(ddof=1)), C.MIN_SD_FRACTION_OF_MEAN * abs(mu))
                tonight = usable[i]
                z = (tonight - mu) / sd if pd.notna(tonight) and sd > 0 else np.nan
            else:
                mu = sd = z = np.nan
            for name, v in zip(names, (mu, sd, n, z)):
                out[name][i] = v
        for name, arr in out.items():
            df[name] = arr
    return df
