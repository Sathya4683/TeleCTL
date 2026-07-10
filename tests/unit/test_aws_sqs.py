"""Tests for :mod:`wactl.integrations.aws.sqs`."""

from __future__ import annotations

from typing import Any

import pytest
from botocore.exceptions import ClientError

from wactl.exceptions import AWSIntegrationError
from wactl.integrations.aws import sqs as sqs_mod


@pytest.fixture(autouse=True)
def _reset_sqs_module() -> None:
    sqs_mod._client = None
    yield
    sqs_mod._client = None


class _FakeSQSClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.received: list[dict[str, Any]] = []
        self.deleted: list[dict[str, Any]] = []
        self.attrs_payload: dict[str, str] = {"ApproximateNumberOfMessages": "3"}
        self.fail_send = False
        self.fail_receive = False

    def send_message(self, **kwargs: Any) -> dict[str, Any]:
        if self.fail_send:
            raise ClientError(
                {"Error": {"Code": "InternalError", "Message": "boom"}},
                "SendMessage",
            )
        self.sent.append(kwargs)
        return {"MessageId": f"mid-{len(self.sent)}"}

    def receive_message(self, **_: Any) -> dict[str, Any]:
        if self.fail_receive:
            raise ClientError(
                {"Error": {"Code": "InternalError", "Message": "boom"}},
                "ReceiveMessage",
            )
        return {"Messages": list(self.received)}

    def delete_message(self, **kwargs: Any) -> dict[str, Any]:
        self.deleted.append(kwargs)
        return {}

    def get_queue_attributes(self, **_: Any) -> dict[str, Any]:
        return {"Attributes": dict(self.attrs_payload)}


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeSQSClient:
    client = _FakeSQSClient()
    monkeypatch.setattr(sqs_mod, "_get_client", lambda: client)
    return client


def test_send_message_returns_message_id(fake_client: _FakeSQSClient) -> None:
    mid = sqs_mod.send_message("https://q", {"job": "x"})
    assert mid == "mid-1"
    assert len(fake_client.sent) == 1
    assert '"job":"x"' in fake_client.sent[0]["MessageBody"]


def test_send_message_with_group_id(fake_client: _FakeSQSClient) -> None:
    sqs_mod.send_message("https://q", {"k": 1}, message_group_id="g1")
    assert fake_client.sent[0].get("MessageGroupId") == "g1"


def test_send_message_omits_group_id_when_none(fake_client: _FakeSQSClient) -> None:
    sqs_mod.send_message("https://q", {"k": 1})
    assert "MessageGroupId" not in fake_client.sent[0]


def test_send_message_failure_raises(fake_client: _FakeSQSClient) -> None:
    fake_client.fail_send = True
    with pytest.raises(AWSIntegrationError):
        sqs_mod.send_message("https://q", {})


def test_receive_message_parses_json(fake_client: _FakeSQSClient) -> None:
    fake_client.received = [
        {
            "MessageId": "m1",
            "ReceiptHandle": "rh1",
            "Body": '{"command":"/pdf-docx","job_id":"j1"}',
        }
    ]
    out = sqs_mod.receive_message("https://q")
    assert len(out) == 1
    assert out[0]["command"] == "/pdf-docx"
    assert out[0]["_receipt_handle"] == "rh1"
    assert out[0]["_message_id"] == "m1"


def test_receive_message_handles_invalid_json(fake_client: _FakeSQSClient) -> None:
    fake_client.received = [{"MessageId": "m1", "ReceiptHandle": "rh", "Body": "not json {"}]
    out = sqs_mod.receive_message("https://q")
    assert out[0]["_raw"].startswith("not json")


def test_receive_message_empty(fake_client: _FakeSQSClient) -> None:
    out = sqs_mod.receive_message("https://q")
    assert out == []


def test_receive_message_failure_raises(fake_client: _FakeSQSClient) -> None:
    fake_client.fail_receive = True
    with pytest.raises(AWSIntegrationError):
        sqs_mod.receive_message("https://q")


def test_delete_message(fake_client: _FakeSQSClient) -> None:
    sqs_mod.delete_message("https://q", "rh-xyz")
    assert fake_client.deleted[0]["ReceiptHandle"] == "rh-xyz"


def test_get_queue_attributes(fake_client: _FakeSQSClient) -> None:
    out = sqs_mod.get_queue_attributes("https://q")
    assert out == {"ApproximateNumberOfMessages": "3"}
