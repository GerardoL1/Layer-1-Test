"""
Apple and Health Auto Export can write the same reading in different units.
Everything is turned into bpm and ms here, and a unit we don't know makes the reading unusable.
"""

from __future__ import annotations

import pandas as pd

from layer1 import config as C


def factor(metric: str, unit) -> float | None:
    """
    What to multiply a value by to get bpm or ms. No unit means the usual one, since most senders leave it out.
    None means a unit we don't know, so guessing would only give a wrong number.
    """
    if unit is None or (isinstance(unit, float) and unit != unit) or not str(unit).strip():
        return 1.0
    return C.UNIT_FACTORS.get(metric, {}).get("".join(str(unit).lower().split()))


def factors(metric: pd.Series, unit: pd.Series) -> pd.Series:
    """factor() for whole columns. NaN where the unit is unknown. Each pair is only looked up once."""
    unit = unit.astype(object).where(unit.notna(), None)
    lookup = {pair: factor(*pair) for pair in set(zip(metric, unit))}
    return pd.Series([lookup[pair] for pair in zip(metric, unit)], index=metric.index, dtype=float)
