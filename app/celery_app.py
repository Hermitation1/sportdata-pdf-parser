import logging
import os

from celery import Celery

logger = logging.getLogger("celery_app")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery("pdf_parser")

celery_app.conf.update(
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    imports=["app.tasks"],
    task_time_limit=3600,
    task_soft_time_limit=3000,
    result_expires=86400,
)

logger.info(f"[celery_app] Tasks registered: {list(celery_app.tasks.keys())}")
