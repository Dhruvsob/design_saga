from core.session_response import login_response


def test_production_login_response_is_cookie_only(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("ALLOW_BEARER_FALLBACK", raising=False)

    assert login_response({"user_id": "user_1"}, "secret-token") == {
        "user": {"user_id": "user_1"},
    }


def test_nonproduction_and_explicit_fallback_can_return_bearer(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    assert login_response({"user_id": "user_1"}, "token")["session_token"] == "token"

    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("ALLOW_BEARER_FALLBACK", "true")
    assert login_response({"user_id": "user_1"}, "token")["session_token"] == "token"
