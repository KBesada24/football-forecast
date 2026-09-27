from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from src.api.dependencies import DatabaseSession

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["connected"]


@router.get("", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse)
def readiness(session: DatabaseSession) -> ReadinessResponse:
    session.execute(text("SELECT 1"))
    return ReadinessResponse(status="ready", database="connected")
