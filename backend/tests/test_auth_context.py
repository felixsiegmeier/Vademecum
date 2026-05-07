import importlib
import utils.auth_context as auth_context


def _reload(monkeypatch, multi_user: str):
    monkeypatch.setenv("MULTI_USER", multi_user)
    importlib.reload(auth_context)
    return auth_context


def test_single_user_mode_always_returns_default(monkeypatch):
    mod = _reload(monkeypatch, "false")
    assert mod.get_user_id() == "default"
    assert mod.get_user_id(authorization="Bearer alice") == "default"
    assert mod.get_user_id(authorization=None) == "default"


def test_multi_user_mode_extracts_bearer_token(monkeypatch):
    mod = _reload(monkeypatch, "true")
    assert mod.get_user_id(authorization="Bearer alice") == "alice"
    assert mod.get_user_id(authorization="Bearer dr.mueller") == "dr.mueller"


def test_multi_user_mode_fallback_to_default_without_header(monkeypatch):
    mod = _reload(monkeypatch, "true")
    assert mod.get_user_id(authorization=None) == "default"
    assert mod.get_user_id(authorization="") == "default"
    assert mod.get_user_id(authorization="Bearer ") == "default"


def test_multi_user_mode_ignores_non_bearer_schemes(monkeypatch):
    mod = _reload(monkeypatch, "true")
    assert mod.get_user_id(authorization="Basic dXNlcjpwYXNz") == "default"
