from app.core.config import APP_NAME, APP_VERSION
from app.schemas.meta import VersionResponse


def get_service_info() -> VersionResponse:
    return VersionResponse(name=APP_NAME, version=APP_VERSION)

