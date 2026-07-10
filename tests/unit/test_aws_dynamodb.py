"""Tests for :mod:`wactl.integrations.aws.dynamodb`."""

from __future__ import annotations

from typing import Any

import pytest
from botocore.exceptions import ClientError

from wactl.exceptions import AWSIntegrationError
from wactl.integrations.aws import dynamodb as ddb_mod


@pytest.fixture(autouse=True)
def _reset_ddb_module() -> None:
    ddb_mod._client = None
    yield
    ddb_mod._client = None


class _FakeDynamoClient:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.put_calls: list[dict[str, Any]] = []

    def put_item(self, **kwargs: Any) -> dict[str, Any]:
        self.put_calls.append(kwargs)
        # Mimic conditional put: fail if pk already present.
        pk = kwargs["Item"]["pk"]["S"]
        condition = kwargs.get("ConditionExpression", "")
        if "attribute_not_exists" in condition and pk in self.items:
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}},
                "PutItem",
            )
        # Convert DDB types back to plain dicts for inspection.
        self.items[pk] = kwargs["Item"]
        return {}


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeDynamoClient:
    client = _FakeDynamoClient()
    monkeypatch.setattr(ddb_mod, "_get_client", lambda: client)
    return client


def test_try_claim_succeeds_first_time(fake_client: _FakeDynamoClient) -> None:
    assert ddb_mod.try_claim("dedup", "wamid-1", ttl_seconds=60) is True
    assert len(fake_client.put_calls) == 1
    item = fake_client.put_calls[0]["Item"]
    assert item["pk"] == {"S": "wamid-1"}
    assert "expires_at" in item


def test_try_claim_returns_false_on_duplicate(fake_client: _FakeDynamoClient) -> None:
    # Pre-populate so the second claim fails the condition.
    fake_client.items["wamid-1"] = {"pk": {"S": "wamid-1"}}
    assert ddb_mod.try_claim("dedup", "wamid-1", ttl_seconds=60) is False


def test_try_claim_with_metadata(fake_client: _FakeDynamoClient) -> None:
    ddb_mod.try_claim(
        "dedup",
        "wamid-2",
        ttl_seconds=60,
        metadata={"command": "/pdf-docx", "priority": 1, "urgent": True},
    )
    item = fake_client.put_calls[0]["Item"]
    assert item["command"] == {"S": "/pdf-docx"}
    assert item["priority"] == {"N": "1"}
    assert item["urgent"] == {"BOOL": True}


def test_try_claim_other_client_error_raises(fake_client: _FakeDynamoClient) -> None:
    def boom(**_: Any) -> dict[str, Any]:
        raise ClientError(
            {"Error": {"Code": "InternalError", "Message": "boom"}},
            "PutItem",
        )

    fake_client.put_item = boom  # type: ignore[method-assign]
    with pytest.raises(AWSIntegrationError):
        ddb_mod.try_claim("dedup", "wamid-1", ttl_seconds=60)
