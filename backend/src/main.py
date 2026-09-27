from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from src.api.body_limit import LineupBodyLimit
from src.api.routers.health import router as health_router
from src.api.routers.lineups import router as lineup_router
from src.api.routers.players import router as player_router
from src.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
    )
    application.add_middleware(LineupBodyLimit)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.include_router(health_router, prefix="/api/v1")
    application.include_router(player_router, prefix="/api/v1")
    application.include_router(lineup_router, prefix="/api/v1")

    @application.exception_handler(SQLAlchemyError)
    async def database_unavailable(_request, _error):
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "code": "database_unavailable",
                    "message": "Data is temporarily unavailable. Please retry.",
                }
            },
        )

    return application


app = create_app()
