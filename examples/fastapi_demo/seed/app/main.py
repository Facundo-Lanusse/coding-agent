from fastapi import FastAPI

from app.routers.health import router as health_router
from app.routers.meta import router as meta_router


def create_app() -> FastAPI:
    application = FastAPI(title="Inventory API", version="0.1.0")
    application.include_router(health_router)
    application.include_router(meta_router)
    return application


app = create_app()

