from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from jose import jwt

from src.api import auth


def test_create_access_token_uses_timezone_aware_exp(monkeypatch):
    settings = SimpleNamespace(
        jwt_access_token_expire_minutes=30,
        jwt_secret_key="test-secret",
        jwt_algorithm="HS256",
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    token = auth.create_access_token({"sub": "alice", "role": "admin"})
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

    exp_timestamp = payload["exp"]
    exp_dt = datetime.fromtimestamp(exp_timestamp, tz=UTC)

    now_utc = datetime.now(UTC)
    delta = exp_dt - now_utc
    assert timedelta(minutes=29) <= delta <= timedelta(minutes=31)


def test_create_access_token_honors_custom_expiry(monkeypatch):
    settings = SimpleNamespace(
        jwt_access_token_expire_minutes=30,
        jwt_secret_key="test-secret",
        jwt_algorithm="HS256",
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)

    token = auth.create_access_token({"sub": "alice"}, expires_delta=timedelta(minutes=5))
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])

    exp_dt = datetime.fromtimestamp(payload["exp"], tz=UTC)
    delta = exp_dt - datetime.now(UTC)
    assert timedelta(minutes=4) <= delta <= timedelta(minutes=6)
