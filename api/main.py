"""BizIntel's FastAPI application entry point."""

from contextlib import asynccontextmanager
import logging

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.deps import validate_session_secret
from api.routes import analytics, ask, auth, dashboard, upload
from db.database import init_db


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_session_secret()
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
async def friendly_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if errors:
        first_err = errors[0]
        loc = [str(x) for x in first_err.get("loc", [])]
        field_name = loc[-1] if loc else "field"
        err_type = first_err.get("type", "")

        if field_name == "password" and "too_short" in err_type:
            msg = "Password must be at least 8 characters long."
        elif field_name == "username" and ("too_short" in err_type or "missing" in err_type):
            msg = "Please enter a valid username."
        elif field_name == "business_name" and ("too_short" in err_type or "missing" in err_type):
            msg = "Please enter your business name."
        elif "too_short" in err_type:
            msg = f"{field_name.replace('_', ' ').title()} is too short."
        else:
            msg = "Please check the information you entered and try again."
    else:
        msg = "Please check the information you entered and try again."

    return JSONResponse(status_code=422, content={"message": msg})


@app.exception_handler(Exception)
async def friendly_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unexpected API error", exc_info=exc)
    return JSONResponse(status_code=500, content={"message": "Something went wrong. Please try again."})


app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(ask.router)
