from fastapi import APIRouter

from app.schemas.processing import HealthCheck

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthCheck)
def health():
    """Open this from the phone's browser to check it can reach the server."""
    return {"ok": True}
