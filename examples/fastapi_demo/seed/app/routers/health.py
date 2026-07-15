from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.services.health import get_liveness

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    return get_liveness()

