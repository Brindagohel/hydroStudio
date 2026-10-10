import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app import config
from app.api.routes import assets, cng, dashboard, hydrotests, inspection
from app.database.connection import create_indexes, get_database
from app.errors import AppError
from app.services import number_plate_service

logger = logging.getLogger("hydrotest")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        create_indexes(get_database())
    except PyMongoError:
        # the API still starts; requests will return a "database unavailable" error
        logger.warning("Could not connect to MongoDB to create indexes. Is it running?")
    if config.PRELOAD_MODELS:
        # load YOLO + EasyOCR in the background so the first camera scan is not slow
        warmup = getattr(number_plate_service, "warmup", None)
        if warmup:
            threading.Thread(target=warmup, name="model-warmup", daemon=True).start()
    yield

app = FastAPI(
    title="Hydrotesting Management & Inspection Workflow",
    description="Asset register, hydrotest records, video inspection, and camera number-plate -> vehicle lookup -> CNG hydrotest verification.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(assets.router)
app.include_router(hydrotests.router)
app.include_router(inspection.router)
app.include_router(cng.router)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, error: AppError):
    return JSONResponse(status_code=error.status_code, content={"detail": error.message})


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, error: RequestValidationError):
    messages = []
    for item in error.errors():
        field = ".".join(str(part) for part in item["loc"] if part not in ("body", "query", "path"))
        text = item["msg"].removeprefix("Value error, ")
        messages.append(f"{field}: {text}" if field else text)
    return JSONResponse(status_code=422, content={"detail": "; ".join(messages)})


@app.exception_handler(PyMongoError)
async def handle_database_error(request: Request, error: PyMongoError):
    logger.error("Database error: %s", type(error).__name__)  # no connection string in the log
    return JSONResponse(status_code=503, content={"detail": "The database is not available right now. Please try again later."})


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, error: Exception):
    logger.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server."})


@app.get("/api/health", tags=["Health"])
def health():
    try:
        get_database().command("ping")
        return {"status": "ok", "database": "up"}
    except PyMongoError:
        return JSONResponse(status_code=503, content={"status": "error", "database": "down"})