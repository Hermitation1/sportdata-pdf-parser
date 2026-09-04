import os
import time

import httpx
import pytest

API_URL = os.getenv("API_URL", "http://localhost:8000")
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
TIMEOUT = httpx.Timeout(10.0)


@pytest.mark.integration
def test_health():
    resp = httpx.get(f"{API_URL}/health", timeout=TIMEOUT)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.integration
def test_full_pipeline():
    # upload
    resp = httpx.post(
        f"{API_URL}/upload/",
        files={"file": ("test.pdf", PDF_BYTES, "application/pdf")},
        timeout=TIMEOUT,
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # poll status until SUCCESS
    status = "PENDING"
    for _ in range(40):
        status = httpx.get(f"{API_URL}/status/{task_id}", timeout=TIMEOUT).json()["status"]
        if status == "SUCCESS":
            break
        time.sleep(0.5)

    assert status == "SUCCESS"

    # result
    result = httpx.get(f"{API_URL}/result/{task_id}", timeout=TIMEOUT)
    assert result.status_code == 200
    assert result.json() == {"mock": True, "task_id": task_id}
