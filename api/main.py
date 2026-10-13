"""BizIntel's FastAPI application entry point."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import analytics, ask, auth, dashboard, upload
from db.database import init_db


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="BizIntel API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(HTTPException)
async def friendly_http_error(_: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "We could not complete that request."
    return JSONResponse(status_code=exc.status_code, content={"message": message})


@app.exception_handler(RequestValidationError)
async def friendly_validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"message": "Please check the information you entered and try again."})


@app.exception_handler(Exception)
async def friendly_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unexpected API error", exc_info=exc)
    return JSONResponse(status_code=500, content={"message": "Something went wrong. Please try again."})


app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(ask.router)
