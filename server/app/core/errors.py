"""Error replies that can always be sent."""

import math

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _json_safe(value):
    """JSON can't hold NaN or Infinity, so those become text."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


async def validation_error(request: Request, exc: Exception) -> JSONResponse:
    """
    FastAPI's own 422 reply. Its default echoes the bad value back, and a NaN or Infinity there made the
    reply itself fail with a 500. Registered for RequestValidationError only.
    """
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(status_code=422, content={"detail": _json_safe(jsonable_encoder(exc.errors()))})
