from unittest.mock import Mock

from src.nonprofit_media import InfraiClient


def test_upload_signing_does_not_replay_by_object_key():
    client = InfraiClient("test-key")
    client.call = Mock()

    for bucket in ("first", "second", "first"):
        client.upload_url(bucket, "receipt.jpg", "image/jpeg")

    assert client.call.call_count == 3
    for call in client.call.call_args_list:
        assert "idempotency_key" not in call.args[2]
        assert call.args[2] == {
            "op": "put", "expires_seconds": 600, "content_type": "image/jpeg"
        }
