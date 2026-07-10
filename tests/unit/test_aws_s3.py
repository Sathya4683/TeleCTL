"""Tests for :mod:`wactl.integrations.aws.s3`."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from botocore.exceptions import ClientError

from wactl.exceptions import AWSIntegrationError
from wactl.integrations.aws import s3 as s3_mod


@pytest.fixture(autouse=True)
def _reset_s3_module() -> None:
    s3_mod._client = None
    yield
    s3_mod._client = None


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._buf = BytesIO(data)

    def read(self) -> bytes:
        return self._buf.getvalue()


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.put_calls.append(kwargs)
        body = kwargs["Body"]
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = data
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "no such key"}},
                "GetObject",
            )
        return {"Body": _FakeBody(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
        return {}

    def generate_presigned_url(
        self,
        op: str,
        *,
        Params: dict[str, Any],
        ExpiresIn: int,
    ) -> str:
        return f"https://signed.example/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}"


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeS3Client:
    client = _FakeS3Client()
    monkeypatch.setattr(s3_mod, "_get_client", lambda: client)
    return client


def test_put_object_bytes(fake_client: _FakeS3Client) -> None:
    s3_mod.put_object("b", "k", b"hello", content_type="text/plain")
    assert fake_client.objects[("b", "k")] == b"hello"
    assert fake_client.put_calls[0]["ContentType"] == "text/plain"


def test_put_object_string(fake_client: _FakeS3Client) -> None:
    s3_mod.put_object("b", "k", "hello")
    assert fake_client.objects[("b", "k")] == b"hello"


def test_put_object_with_metadata(fake_client: _FakeS3Client) -> None:
    s3_mod.put_object("b", "k", b"x", metadata={"user": "u1"})
    assert fake_client.put_calls[0]["Metadata"] == {"user": "u1"}


def test_get_object_returns_bytes(fake_client: _FakeS3Client) -> None:
    fake_client.objects[("b", "k")] = b"data-here"
    assert s3_mod.get_object("b", "k") == b"data-here"


def test_get_object_missing_raises(fake_client: _FakeS3Client) -> None:
    with pytest.raises(AWSIntegrationError):
        s3_mod.get_object("b", "missing")


def test_object_exists_true(fake_client: _FakeS3Client) -> None:
    fake_client.objects[("b", "k")] = b"x"
    assert s3_mod.object_exists("b", "k") is True


def test_object_exists_false_on_404(fake_client: _FakeS3Client) -> None:
    assert s3_mod.object_exists("b", "missing") is False


def test_object_exists_other_error_raises(fake_client: _FakeS3Client) -> None:
    # Inject an unexpected error from head_object
    def boom(**_: Any) -> dict[str, Any]:
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}},
            "HeadObject",
        )

    fake_client.head_object = boom  # type: ignore[method-assign]
    with pytest.raises(AWSIntegrationError):
        s3_mod.object_exists("b", "k")


def test_presigned_get_url(fake_client: _FakeS3Client) -> None:
    url = s3_mod.presigned_get_url("b", "k", expires_in=120)
    assert "signed.example" in url
    assert "b/k" in url
    assert "expires=120" in url


def test_make_key_joins_and_strips_slashes() -> None:
    assert s3_mod.make_key("a", "b", "c") == "a/b/c"
    assert s3_mod.make_key("a/", "/b/", "c") == "a/b/c"
    assert s3_mod.make_key("", "a", "", "b") == "a/b"
