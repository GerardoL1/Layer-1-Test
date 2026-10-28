"""
Recovery platform server (API only). This file only puts the app together. The code lives in app/.

The API is under /api/v1, and everything about one person under /api/v1/users/{user_id}.
Four ways data can arrive (all land in the same database):
  1. Our iPhone app                  POST .../readings                     app/routers/readings.py
  2. Health Auto Export iPhone app   POST .../readings/health-auto-export  app/routers/readings.py
  3. Apple Shortcuts automation      POST .../readings/shortcuts           app/routers/readings.py
  4. Apple Health export file        POST .../imports                      app/routers/imports.py
                                     (or python import_export.py)

Every reading is stored with its UTC offset so nights can be worked out in local time.
After new data arrives the Layer 1 preprocessing runs in the background (app/services/processing.py).

Run:
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.core import db
from app.core.errors import validation_error
from app.middleware.size_limit import LimitRequestSize
from app.routers import (
    checkins,
    demo,
    health,
    imports,
    processing_runs,
    profile,
    readings,
    settings,
    sweat,
    today,
    trends,
    workouts,
)
from app.services import processing
from app.services import sweat as sweat_store

# One log format for the whole server. Each line shows the time, level and which part wrote it.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Recovery platform", version="1")

for module in (
    health,
    readings,
    imports,
    today,
    trends,
    profile,
    settings,
    checkins,
    workouts,
    sweat,
    processing_runs,
    demo,
):
    app.include_router(module.router)
app.include_router(sweat.demo_router)
app.add_exception_handler(RequestValidationError, validation_error)

# Added before CORS so CORS wraps it: the app in a browser can then read the 413 message.
app.add_middleware(LimitRequestSize)
# Wide open for testing only.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db.init_db()
processing.init_db()
sweat_store.init_db()
