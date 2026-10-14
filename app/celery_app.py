"""Конфигурация Celery: Redis как брокер и result backend, JSON-сериализация, лимиты задач."""

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
    broker_connection_retry_on_startup=True,
    worker_concurrency=1,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

logger.info(f"[celery_app] Configured task imports: {celery_app.conf.imports}")
