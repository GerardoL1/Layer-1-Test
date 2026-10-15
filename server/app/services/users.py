"""Looking up a user: their settings, latest run and saved nights."""

import json

import pandas as pd
from fastapi import HTTPException

from app.core import db
from app.services import processing


def require_user(conn, user_id: str):
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(404, f"No data for '{user_id}' yet. Sync from the iPhone or import a Health export.")
    return user


def last_run(conn, user_id: str):
    return conn.execute("SELECT * FROM runs WHERE user_id = ? ORDER BY run DESC LIMIT 1", (user_id,)).fetchone()


def night_rows(user_id: str) -> pd.DataFrame:
    with db.connect() as conn:
        return processing.load_nights(conn, user_id)


def read_settings(user_id: str) -> dict:
    with db.connect() as conn:
        user = require_user(conn, user_id)
    return {
        "timezone": user["timezone"],
        "update_time": user["update_time"],
        "age": user["age"],
        "training": user["training"],
        "training_days": json.loads(user["training_days"]) if user["training_days"] else [],
        "units": user["units"] or "metric",
    }
