import uuid
from pathlib import Path

from rq.exceptions import NoSuchJobError
from rq.job import Job

from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Query
from fastapi.responses import FileResponse, JSONResponse
from starlette import status

from app.schemas.transcriptions import RedactionResponse

from app.utils.redis_client import get_redis
from app.utils.queue import get_queue

from app.utils.tasks import process_job
from app.utils.limiter import limiter
from app.utils.history import get_history, get_history_entry, delete_history_entry
from app.core.config import settings

router = APIRouter(prefix="/transcriptions", tags=["transcriptions"])
queue = get_queue()

@router.post("/redact")
@limiter.limit("5/minute")
async def redact_file(
        request: Request,
        file: UploadFile = File(...)
):
    allowed_extensions = settings.ALLOWED_EXTENSIONS
    suffix = Path(file.filename).suffix.lower()

    if suffix not in allowed_extensions:
        raise HTTPException(400, detail="Unsupported file type")

    job_id = str(uuid.uuid4())
    input_path = settings.UPLOAD_DIR / f"{job_id}{suffix}"
    output_dir = str(settings.OUTPUT_DIR / job_id)

    input_path.write_bytes(await file.read())
    job = queue.enqueue(
        process_job,
        args=(str(input_path), output_dir),
        job_id=job_id
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"job_id": job_id, "status": "created"})


@router.get("/redact/{job_id}", response_model=RedactionResponse)
async def get_job_status(job_id: str):
    redis = get_redis()
    try:
        job = Job.fetch(job_id, connection=redis)
    except NoSuchJobError:
        raise HTTPException(404, detail="Job not found")

    if job.is_finished:
        result = job.return_value()
        if result is None:
            raise HTTPException(500, detail="Job finished but returned no result")

        return JSONResponse(content={"status": "done", **result})

    elif job.is_failed:
        return JSONResponse(content={
            "status": "failed",
            "error": str(job.latest_result().exc_string)
        })

    else:
        return JSONResponse(content={"status": job.get_status().value})


@router.get("/redact/{job_id}/audio")
async def get_redacted_audio(job_id: str):
    job = Job.fetch(job_id, connection=get_redis())
    if not job.is_finished:
        raise HTTPException(400, detail="Job not finished")

    result = job.return_value()
    if result is None:
        raise HTTPException(500, detail="No result available")

    audio_path = result.get("redacted_audio_url")
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(404, detail="Audio file not found")

    return FileResponse(audio_path, media_type="audio/wav", filename="redacted.wav")

@router.get("/redact/{job_id}/log")
async def get_redaction_log(job_id: str):
    job = Job.fetch(job_id, connection=get_redis())
    if not job.is_finished:
        raise HTTPException(400, detail="Job not finished")

    result = job.return_value()
    if result is None:
        raise HTTPException(500, detail="No result available")

    entities = result.get("entities", [])
    report = {}
    for entity in entities:
        t = entity["type"]
        report.setdefault(t, []).append(entity["text"])

    return JSONResponse(content={
        "job_id": job_id,
        "total_redacted": len(entities),
        "by_type": report
    })

@router.get("/history")
async def list_history(
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    entity_type: str | None = Query(
        default=None,
        description="Filter by PII type: PERSON, PHONE, EMAIL, ADDRESS, INN, SNILS, PASPORT",
    ),
):
    """
    Return paginated processing history, newest first.
 
    Each item contains:
    - **job_id** – unique identifier
    - **filename** – original uploaded file name
    - **created_at** – ISO-8601 UTC timestamp
    - **duration_sec** – audio duration in seconds
    - **total_redacted** – total number of redacted entities
    - **entity_types** – list of unique PII-type tags found (e.g. ["PERSON", "PHONE"])
    - **status** – `done` or `failed`
    """
    result = get_history(
        page=page,
        page_size=page_size,
        entity_type_filter=entity_type,
    )
    return JSONResponse(content=result)
 
 
@router.get("/history/{job_id}")
async def get_history_item(job_id: str):
    """Return the history record for a single job."""
    entry = get_history_entry(job_id)
    if not entry:
        raise HTTPException(404, detail="History entry not found")
    return JSONResponse(content=entry)
 
 
@router.delete("/history/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_history_item(job_id: str):
    """Delete a history record (does NOT delete the RQ job or files)."""
    deleted = delete_history_entry(job_id)
    if not deleted:
        raise HTTPException(404, detail="History entry not found")