from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """Open this from the phone's browser to check it can reach the server."""
    return {"ok": True}
