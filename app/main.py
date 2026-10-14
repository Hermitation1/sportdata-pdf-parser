import logging
import os
import uuid

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from celery.result import AsyncResult
from app.callback_validation import validate_callback_url
from app.celery_app import celery_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(message)s")
logger = logging.getLogger("api")

app = FastAPI()

os.makedirs("files", exist_ok=True)

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024


@app.get("/health")
def health():
    try:
        with celery_app.connection() as conn:
            conn.ensure_connection(max_retries=1)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Redis unavailable")


@app.post("/upload/")
def upload_pdf(file: UploadFile = File(...), callback_url: str | None = Form(None)):
    if callback_url:
        try:
            validate_callback_url(callback_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    task_id = str(uuid.uuid4())
    file_path = f"files/{task_id}.pdf"

    try:
        with open(file_path, "wb") as buffer:
            size = 0
            first_chunk = True
            while chunk := file.file.read(1024 * 1024):
                if first_chunk:
                    first_chunk = False
                    if b"%PDF" not in chunk[:1024]:
                        raise HTTPException(status_code=400, detail="Not a valid PDF file")
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_MB} MB)")
                buffer.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Empty file")
    except HTTPException:
        os.remove(file_path)
        raise

    celery_app.send_task("app.tasks.parse_pdf", args=[task_id, callback_url], task_id=task_id)
    logger.info(f"Queued: {task_id} ({file.filename!r}, {size} bytes)")

    return {"task_id": task_id, "status": "queued"}


@app.get("/status/{task_id}")
def task_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    return {"task_id": task_id, "status": result.status}


@app.get("/result/{task_id}")
def task_result(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    if not result.ready():
        raise HTTPException(status_code=202, detail=f"Still {result.status}")
    if result.failed():
        logger.error(f"Task failed: {task_id}")
        raise HTTPException(status_code=500, detail="Task failed")
    return result.result


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
