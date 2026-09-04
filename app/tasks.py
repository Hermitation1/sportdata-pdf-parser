"""Celery-таски: OCR + LLM-экстракция + callback — всё в одном."""

import logging
import os
from pathlib import Path

import httpx
from celery import shared_task

from app.callback_validation import validate_callback_url
from app.services import process_pdf, extract_contest_json

logger = logging.getLogger("celery")


def _send_callback(task_id: str, callback_url: str, result: dict) -> None:
    """Доставка результата на callback_url. Сбой логируется, но не роняет задачу."""
    try:
        validate_callback_url(callback_url)
        resp = httpx.post(callback_url, json={"task_id": task_id, "result": result}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Callback failed for {task_id}: {e}")


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def parse_pdf(self, task_id: str, callback_url: str | None = None) -> dict:
    """PDF → OCR → Markdown → LLM → JSON. Всё в одной таске."""
    file_path = f"files/{task_id}.pdf"

    if os.getenv("MOCK_PARSE", "").strip() == "1":
        result = {"mock": True, "task_id": task_id}
        if callback_url:
            _send_callback(task_id, callback_url, result)
        return result

    try:
        md_path = f"files/{task_id}.md"

        # Шаг 1: OCR (пропускаем, если markdown уже есть — при retry)
        if not Path(md_path).exists():
            logger.info(f"OCR: {task_id}")
            process_pdf(file_path, task_id)
        else:
            logger.info(f"Reusing existing markdown: {task_id}")

        # Шаг 2: LLM
        markdown = Path(md_path).read_text(encoding="utf-8")
        logger.info(f"LLM: {task_id} ({len(markdown)} chars)")
        result = extract_contest_json(markdown)

        # Шаг 3: Callback
        if callback_url:
            _send_callback(task_id, callback_url, result)

        return result

    except FileNotFoundError:
        logger.error(f"Markdown not found for {task_id}")
        raise
    except Exception as e:
        logger.error(f"Failed {task_id}: {e}")
        raise self.retry(exc=e)
