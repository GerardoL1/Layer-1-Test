"""
Recovery platform server (API only). This file only puts the app together. The code lives in app/.

Four ways data can arrive (all land in the same database):
  1. Our iPhone app                  POST /upload         app/routers/readings.py
  2. Health Auto Export iPhone app   POST /api/hae        app/routers/readings.py
  3. Apple Shortcuts automation      POST /api/shortcut   app/routers/readings.py
  4. Apple Health export file        POST /api/import     app/routers/imports.py  (or python import_export.py)

Every reading is stored with its UTC offset so nights can be worked out in local time.
After new data arrives the Layer 1 preprocessing runs in the background (app/services/processing.py).

Run:
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import db
from app.middleware.size_limit import LimitRequestSize
from app.routers import demo, health, imports, profile, readings, settings, today, trends, update_now
from app.services import processing

# One log format for the whole server. Each line shows the time, level and which part wrote it.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Recovery platform")

for module in (today, trends, profile, settings, update_now, demo, health, readings, imports):
    app.include_router(module.router)

# Added before CORS so CORS wraps it: the app in a browser can then read the 413 message.
app.add_middleware(LimitRequestSize)
# Wide open for testing only.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db.init_db()
processing.init_db()
