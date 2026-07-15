from app.schemas.health import HealthResponse


def get_liveness() -> HealthResponse:
    return HealthResponse(status="ok", checks={"process": "up"})

