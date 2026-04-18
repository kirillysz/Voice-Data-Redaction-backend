import uuid
from pathlib import Path

from rq.exceptions import NoSuchJobError
from rq.job import Job

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette import status

from app.schemas.transcriptions import RedactionResponse

from app.utils.redis_client import get_redis
from app.utils.queue import get_queue

from app.utils.tasks import process_job
from app.utils.limiter import limiter
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