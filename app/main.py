import json
import logging
import os
import uuid
from pathlib import Path

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
    except Exception:
        raise HTTPException(status_code=503, detail="Redis unavailable")


@app.post("/upload/")
def upload_pdf(file: UploadFile = File(...), callback_url: str | None = Form(None)):
    if callback_url:
        try:
            validate_callback_url(callback_url)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    task_id = str(uuid.uuid4())
    file_path = f"files/{task_id}.pdf"

    try:
        with open(file_path, "wb") as buffer:
            size = 0
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_MB} MB)")
                buffer.write(chunk)
    except HTTPException:
        os.remove(file_path)
        raise

    celery_app.send_task("app.tasks.parse_pdf", args=[task_id, callback_url], task_id=task_id)
    logger.info(f"Queued: {task_id} ({file.filename}, {size} bytes)")

    return {"task_id": task_id, "status": "queued"}


@app.get("/status/{task_id}")
async def task_status(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    return {"task_id": task_id, "status": result.status}


@app.get("/result/{task_id}")
async def task_result(task_id: str):
    result = AsyncResult(task_id, app=celery_app)
    if result.ready():
        return result.result
    raise HTTPException(status_code=202, detail=f"Still {result.status}")


# @app.post("/extract-contest/{task_id}") # curl.exe -X POST http://localhost:8000/extract-contest/{task_id}
# async def extract_contest(task_id: str):
#     """Шаг 2: Markdown → JSON по модели фронтенда."""
#     md_path = f"files/{task_id}.md"
#     if not os.path.exists(md_path):
#         raise HTTPException(status_code=404, detail="Markdown не найден. Сначала загрузите PDF через /upload/")
#
#     try:
#         markdown = Path(md_path).read_text(encoding="utf-8")
#         logger.info(f"Extracting JSON from: {task_id} ({len(markdown)} chars)")
#         return extract_contest_json(markdown)
#     except json.JSONDecodeError as e:
#         raise HTTPException(status_code=500, detail=f"LLM returned invalid JSON: {e}")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
