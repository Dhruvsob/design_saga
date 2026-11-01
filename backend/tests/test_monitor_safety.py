import inspect
from pathlib import Path

from core.jobs import _safe_job_error
from routes.organization import upload_logo_multipart


MONITOR = (Path(__file__).parents[2] / "deploy" / "monitor.sh").read_text(encoding="utf-8")


def test_monitor_alerts_on_repeated_backend_5xx_responses():
    assert "DESIGN_SAGA_MAX_BACKEND_5XX_COUNT" in MONITOR
    assert 'docker logs --since 5m "$backend_cid"' in MONITOR
    assert "HTTP/[0-9.]+\" 5[0-9][0-9]" in MONITOR
    assert "HTTP 5xx responses in five minutes" in MONITOR


def test_monitor_validates_5xx_threshold_as_an_integer():
    settings_block = MONITOR.split("for setting in", 1)[1].split("done", 1)[0]
    assert '"$max_backend_5xx_count"' in settings_block


def test_job_failure_state_does_not_persist_exception_secrets():
    error = RuntimeError("DO_NOT_PERSIST_PRIVATE_PROVIDER_DETAIL_7f3a")
    assert _safe_job_error(error) == "RuntimeError"


def test_logo_upload_does_not_return_raw_storage_errors():
    source = inspect.getsource(upload_logo_multipart)
    assert "Storage error: {e}" not in source
    assert "Logo storage is temporarily unavailable" in source
