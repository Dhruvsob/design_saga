from pathlib import Path


MONITOR = (Path(__file__).parents[2] / "deploy" / "monitor.sh").read_text(encoding="utf-8")


def test_monitor_alerts_on_repeated_backend_5xx_responses():
    assert "DESIGN_SAGA_MAX_BACKEND_5XX_COUNT" in MONITOR
    assert 'docker logs --since 5m "$backend_cid"' in MONITOR
    assert "HTTP/[0-9.]+\" 5[0-9][0-9]" in MONITOR
    assert "HTTP 5xx responses in five minutes" in MONITOR


def test_monitor_validates_5xx_threshold_as_an_integer():
    settings_block = MONITOR.split("for setting in", 1)[1].split("done", 1)[0]
    assert '"$max_backend_5xx_count"' in settings_block
