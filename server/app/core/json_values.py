"""Turning pandas and numpy values into plain JSON values."""

import math
from datetime import date, datetime

import pandas as pd


def clean(v):
    """JSON can't hold NaN, so missing numbers become null."""
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    if hasattr(v, "item"):  # numpy numbers
        return clean(v.item())
    return v


def r1(v):
    v = clean(v)
    return round(v, 1) if isinstance(v, float) else v
