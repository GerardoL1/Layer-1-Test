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
    dates = pd.to_datetime(df["night_date"])
    rows = range(len(df)) if only_dates is None else [i for i, d in enumerate(df["night_date"]) if d in set(only_dates)]
    for col, (zcol, _label, gate) in C.ZSCORE_METRICS.items():
        usable = df[col].where(df[gate].fillna(False).astype(bool))
        for name in (f"{col}_base_mean", f"{col}_base_sd", f"{col}_base_n", zcol):
            if name not in df:
                df[name] = np.nan
        for i in rows:
            d = dates.iloc[i]
            window = (dates >= d - pd.Timedelta(days=C.BASELINE_WINDOW_NIGHTS)) & (dates < d)
            vals = usable[window].dropna()
            n = len(vals)
            if n >= C.BASELINE_MIN_NIGHTS:
                mu = float(vals.mean())
                sd = max(float(vals.std(ddof=1)), C.MIN_SD_FRACTION_OF_MEAN * abs(mu))
                tonight = usable.iloc[i]
                z = (tonight - mu) / sd if pd.notna(tonight) and sd > 0 else np.nan
            else:
                mu = sd = z = np.nan
            df.iloc[i, df.columns.get_loc(f"{col}_base_mean")] = mu
            df.iloc[i, df.columns.get_loc(f"{col}_base_sd")] = sd
            df.iloc[i, df.columns.get_loc(f"{col}_base_n")] = n
            df.iloc[i, df.columns.get_loc(zcol)] = z
    return df
