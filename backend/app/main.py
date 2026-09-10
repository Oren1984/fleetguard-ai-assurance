"""FleetGuard AI - FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.config import settings
from app.database import SessionLocal, init_db
from app.exceptions import (
    ApprovalRequiredError,
    FleetGuardError,
    InvalidTelemetryError,
    KillSwitchEngagedError,
    SopNotFoundError,
    WeatherServiceError,
)
from app.logging_config import configure_logging, get_logger
from app.routers import admin, approvals, audit_router, health, risk, trucks
from app.seed import seed_if_empty

configure_logging()
logger = get_logger("fleetguard.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.SEED_ON_STARTUP:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    logger.info("fleetguard_startup_complete")
    yield


app = FastAPI(
    title="FleetGuard AI",
    description="AI-assisted cold-chain risk detection and incident response for refrigerated fleets.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(trucks.router)
app.include_router(risk.router)
app.include_router(approvals.router)
app.include_router(audit_router.router)
app.include_router(admin.router)


_ERROR_STATUS = {
    InvalidTelemetryError: 422,
    WeatherServiceError: 502,
    SopNotFoundError: 404,
    KillSwitchEngagedError: 423,
    ApprovalRequiredError: 403,
}


@app.exception_handler(FleetGuardError)
async def fleetguard_error_handler(request: Request, exc: FleetGuardError):
    status_code = _ERROR_STATUS.get(type(exc), 400)
    logger.warning(
        "domain_error",
        extra={"extra_fields": {"error_type": type(exc).__name__, "message": str(exc), "path": str(request.url)}},
    )
    return JSONResponse(status_code=status_code, content={"detail": str(exc), "error_type": type(exc).__name__})


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
def root():
    return {"service": "FleetGuard AI", "status": "running", "docs": "/docs"}
