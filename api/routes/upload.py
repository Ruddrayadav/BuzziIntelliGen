"""Stateless upload routes that delegate all processing to upload services."""

import hashlib
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from api.deps import SessionUser, require_session
from api.detector import detect_file_type
from api.serializers import to_jsonable
from config import settings
from services.upload_service import execute_upload, read_file, suggest_mapping_from_file, validate_file


router = APIRouter(prefix="/api/upload", tags=["upload"])


def _check_content_length(request: Request) -> None:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            length_bytes = int(content_length)
            if length_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"The uploaded file is too large ({length_bytes / (1024 * 1024):.1f} MB). The maximum allowed size is {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.",
                )
        except ValueError:
            pass


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    filename = file.filename or "upload.csv"
    chunk_size = 64 * 1024
    total_bytes = bytearray()

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_bytes.extend(chunk)
        if len(total_bytes) > settings.MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"The uploaded file exceeds the maximum allowed size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB.",
            )

    return bytes(total_bytes), filename


@router.post("/preview")
async def preview_upload(
    request: Request,
    file: UploadFile = File(...),
    file_type: str | None = Form(default=None),
    user: SessionUser = Depends(require_session),
):
    del user  # Authentication is required even though preview does not write data.
    _check_content_length(request)
    try:
        file_bytes, filename = await _read_upload(file)
        validate_file(file_bytes, filename)
        raw_df = read_file(file_bytes, filename)
        detected_type = detect_file_type(raw_df.columns.tolist())
        selected_type = file_type or detected_type
        preview = suggest_mapping_from_file(file_bytes, filename, selected_type, use_llm=False)
        file_hash = hashlib.sha256(file_bytes).hexdigest()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return to_jsonable({
        "filename": preview.filename,
        "file_hash": file_hash,
        "detected_type": detected_type,
        "file_type": preview.file_type,
        "columns": preview.column_names,
        "suggested_mapping": preview.suggested.suggested,
        "mapping_methods": preview.suggested.method,
        "missing_required": preview.suggested.missing_required,
        "sample_rows": preview.sample_rows,
        "raw_row_count": preview.raw_row_count,
    })


@router.post("/commit")
async def commit_upload(
    request: Request,
    file: UploadFile = File(...),
    file_type: str = Form(...),
    mapping: str = Form(...),
    mode: str = Form(default="commit"),
    replace: bool = Form(default=False),
    user: SessionUser = Depends(require_session),
):
    _check_content_length(request)
    try:
        confirmed_mapping = json.loads(mapping)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mapping must be valid JSON.")
    if not isinstance(confirmed_mapping, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Mapping must be a JSON object.")

    try:
        file_bytes, filename = await _read_upload(file)
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        # Re-read on every commit: the API keeps no upload state between requests.
        preview = suggest_mapping_from_file(file_bytes, filename, file_type, use_llm=False)
        result = execute_upload(
            raw_df=preview.raw_df,
            confirmed_mapping=confirmed_mapping,
            file_type=file_type,
            filename=filename,
            tenant_id=user.tenant_id,
            file_hash=file_hash,
            replace_existing=(mode == "replace" or replace),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if not result.success:
        if result.is_duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=result.error_message,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error_message or "We could not import that file. Please check it and try again.",
        )

    response = {
        "success": result.success,
        "upload_log_id": result.upload_log_id,
        "filename": result.filename,
        "file_type": result.file_type,
        "rows_read": result.raw_count,
        "rows_saved": result.clean_count,
        "rows_skipped": result.invalid_removed,
        "duplicates_removed": result.duplicates_removed,
        "skipped_rows": result.rejected_rows_detailed,
        "warnings": result.warnings,
        "error_message": result.error_message,
    }
    return to_jsonable(response)

