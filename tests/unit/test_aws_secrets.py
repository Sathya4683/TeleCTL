"""Tests for :mod:`wactl.integrations.aws.secrets`."""

from __future__ import annotations

import pytest
from botocore.exceptions import ClientError

from wactl.exceptions import AWSIntegrationError
from wactl.integrations.aws import secrets as secrets_mod


@pytest.fixture(autouse=True)
def _reset_secrets_module() -> None:
    """Clear module-level cache + client between tests."""
    secrets_mod.clear_cache()
    secrets_mod._client = None
    yield
    secrets_mod.clear_cache()
    secrets_mod._client = None


def _make_client_with_value(value: str) -> object:
    """Patch the module-level _get_client to return a fake boto3 client."""

    class _FakeClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            if SecretId == "missing":
                raise ClientError(
                    {"Error": {"Code": "ResourceNotFoundException", "Message": "not found"}},
                    "GetSecretValue",
                )
            return {"SecretString": value}

    return _FakeClient()


def test_get_secret_returns_value(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _make_client_with_value("super-secret-value")
    monkeypatch.setattr(secrets_mod, "_get_client", lambda: fake)
    assert secrets_mod.get_secret("my/secret") == "super-secret-value"


def test_get_secret_caches_value(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = {"n": 0}

    class _FakeClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            call_count["n"] += 1
            return {"SecretString": "v1"}

    monkeypatch.setattr(secrets_mod, "_get_client", lambda: _FakeClient())
    assert secrets_mod.get_secret("my/secret") == "v1"
    # Second call should be served from cache.
    assert secrets_mod.get_secret("my/secret") == "v1"
    assert call_count["n"] == 1


def test_get_secret_client_error_raises_aws_integration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _make_client_with_value("ignored")
    monkeypatch.setattr(secrets_mod, "_get_client", lambda: fake)
    with pytest.raises(AWSIntegrationError):
        secrets_mod.get_secret("missing")


def test_get_secret_no_secret_string_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            return {}  # no SecretString

    monkeypatch.setattr(secrets_mod, "_get_client", lambda: _FakeClient())
    with pytest.raises(AWSIntegrationError):
        secrets_mod.get_secret("binary-only-secret")


def test_clear_cache_forces_refetch(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = {"n": 0}

    class _FakeClient:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            call_count["n"] += 1
            return {"SecretString": "v1"}

    monkeypatch.setattr(secrets_mod, "_get_client", lambda: _FakeClient())
    assert secrets_mod.get_secret("k") == "v1"
    secrets_mod.clear_cache()
    assert secrets_mod.get_secret("k") == "v1"
    assert call_count["n"] == 2


def test_default_cache_ttl_constant() -> None:
    assert secrets_mod.DEFAULT_CACHE_TTL_SECONDS == 300
