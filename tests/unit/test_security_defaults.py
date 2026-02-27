import pytest

from src.config.settings import Settings


def _make_settings(**overrides):
    base = {
        "gitlab_token": "test-token",
        "database_url": "sqlite+aiosqlite:///./test.db",
        "api_secret_key": "api-secret",
        "jwt_secret_key": "jwt-secret",
    }
    base.update(overrides)
    return Settings(**base)


def test_secure_defaults_enabled():
    settings = _make_settings()

    assert settings.mcp_auth_enabled is True
    assert settings.azuredevops_ssl_verify is True


def test_default_cors_origins_are_explicit_not_wildcard():
    settings = _make_settings()

    assert "*" not in settings.api_cors_origins
    assert "http://localhost:3000" in settings.api_cors_origins
    assert "http://127.0.0.1:3000" in settings.api_cors_origins


def test_testing_environment_allows_missing_secrets(monkeypatch):
    monkeypatch.delenv("gitlab_token", raising=False)
    monkeypatch.delenv("api_secret_key", raising=False)
    monkeypatch.delenv("jwt_secret_key", raising=False)

    settings = Settings(environment="testing", database_url="sqlite+aiosqlite:///./test.db")

    assert settings.gitlab_token == ""
    assert settings.api_secret_key == ""
    assert settings.jwt_secret_key == ""


def test_non_testing_environment_requires_critical_secrets(monkeypatch):
    for key in ("gitlab_token", "api_secret_key", "jwt_secret_key"):
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.upper(), raising=False)

    with pytest.raises(ValueError, match="Missing required settings"):
        Settings(environment="development", database_url="sqlite+aiosqlite:///./test.db")


def test_non_testing_environment_rejects_whitespace_only_secrets():
    with pytest.raises(ValueError, match="Missing required settings"):
        Settings(
            environment="development",
            database_url="sqlite+aiosqlite:///./test.db",
            gitlab_token="   ",
            api_secret_key="\t",
            jwt_secret_key="\n",
        )
