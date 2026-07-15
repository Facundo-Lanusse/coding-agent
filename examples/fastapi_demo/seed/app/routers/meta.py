from fastapi import APIRouter

from app.schemas.meta import VersionResponse
from app.services.version import get_service_info

router = APIRouter(tags=["metadata"])


@router.get("/info", response_model=VersionResponse)
def service_info() -> VersionResponse:
    return get_service_info()

