# PDF-парсер спортивных отчётов

Сервис парсинга PDF-отчётов о соревнованиях: распознавание документа (OCR) и извлечение призёров (1–3 место) в структурированный JSON. Обработка асинхронная — файл ставится в очередь, результат забирается по `task_id`.

## Стек

- FastAPI + uvicorn — HTTP API
- Celery + Redis — асинхронная очередь и result backend
- docling + RapidOCR — распознавание текста (GPU, русские ONNX-модели)
- DeepSeek API — LLM-экстракция призёров
- Docker + uv — сборка и зависимости

## Сервисы

- `api` — лёгкий FastAPI (приём файла и постановка в очередь)
- `celery-worker` — тяжёлый (OCR + LLM-экстракция)
- `redis` — брокер и result backend

## Docker-образы

- `base` — `nvidia/cuda` + ML-зависимости (docling, torch, onnxruntime)
- `api` — лёгкий (`python:3.12-slim`)
- `worker` — тонкий (`FROM base`, быстрая пересборка)

## Быстрый старт

1. Создать `.env` с ключом:

```
DEEPSEEK_API_KEY=sk-...
```

2. Собрать и поднять:

```powershell
docker compose up -d
```

3. Загрузить PDF:

```powershell
curl.exe -X POST http://localhost:8000/upload/ -F "file=@report.pdf;type=application/pdf"
```

В ответ придёт `{"task_id": "...", "status": "queued"}`. Дальше:

```powershell
curl.exe http://localhost:8000/status/ТВОЙ_TASK_ID
curl.exe http://localhost:8000/result/ТВОЙ_TASK_ID
```

## API

- `POST /upload/` — принимает PDF (multipart) и опциональный `callback_url`, возвращает `task_id`
- `GET /status/{task_id}` — статус задачи (`PENDING`/`SUCCESS`/`FAILURE`)
- `GET /result/{task_id}` — готовый JSON или `202`, если ещё обрабатывается
- `GET /health` — `{"status": "ok"}` или `503`, если Redis недоступен

Валидация на `/upload/`: только PDF, лимит размера, whitelist хостов для `callback_url` (SSRF-защита).

## Env-переменные

- `DEEPSEEK_API_KEY` — обязателен, ключ DeepSeek API
- `CALLBACK_ALLOWED_HOSTS` — whitelist хостов для callback (через запятую); пусто = callback отключён
- `MAX_UPLOAD_MB` — лимит размера файла (по умолчанию 50)
- `REDIS_URL` — адрес Redis (по умолчанию `redis://redis:6379/0`)
- `MOCK_PARSE=1` — mock-режим воркера (для тестов, пропускает OCR/LLM)

## Тесты

Unit (локально, стек не нужен):

```powershell
uv run pytest
```

Integration (изолированный стек, рабочий не трогается):

```powershell
set "MOCK_PARSE=1" && set "API_PORT=8001" && docker compose -p pdfparser-test up -d --build
set "API_URL=http://localhost:8001" && uv run pytest -m integration
docker compose -p pdfparser-test down
```

## Встраивание в чужой compose

Сервисы переносятся как есть — `api`, `celery-worker`, `redis`. Заказчику нужны:

- volumes: `./files:/app/files`, `./hf_cache:/root/.cache/huggingface`, `./paddleocr_models:/app/paddleocr_models`
- env: `DEEPSEEK_API_KEY`, `CALLBACK_ALLOWED_HOSTS` (имя фронта заказчика), `REDIS_URL` (при своём Redis)
- GPU-доступ для `celery-worker` (`deploy.resources.reservations.devices` с `driver: nvidia`)

## Как это работает (кратко)

`POST /upload/` → файл в `files/{task_id}.pdf` → задача `parse_pdf` в Redis → воркер: OCR (docling/RapidOCR на GPU) → markdown → LLM-экстракция (DeepSeek, header + батчи по протоколам) → JSON призёров → result backend (+ опциональный `callback_url`).
