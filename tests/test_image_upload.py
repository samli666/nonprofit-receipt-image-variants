import base64
from unittest.mock import Mock

import pytest

from src.nonprofit_media import ReceiptMediaWorkflow, VariantRequest


def test_variant_uploads_downloaded_bytes(monkeypatch):
    client = Mock()
    client.download_url.return_value = {"url": "https://storage.example/signed"}
    client.upload_image.return_value = {"image_id": "uploaded", "url": "https://storage.example/uploaded"}
    client.resize_image.return_value = {"image_id": "resized", "url": "data:image/webp;base64,resized-bytes"}
    client.compress_image.return_value = {"image_id": "compressed", "url": "https://storage.example/compressed"}
    response = Mock(content=b"image bytes")
    download = Mock(return_value=response)
    monkeypatch.setattr("src.nonprofit_media.requests.get", download)

    result = ReceiptMediaWorkflow(client, "receipts").build_variant(
        VariantRequest(key="receipts/test.png", width=120, height=90)
    )

    download.assert_called_once_with("https://storage.example/signed", timeout=30)
    response.raise_for_status.assert_called_once_with()
    client.upload_image.assert_called_once_with(
        base64.b64encode(b"image bytes").decode("ascii"), "test.png"
    )
    client.resize_image.assert_called_once_with({"image_id": "uploaded"}, 120, 90)
    client.compress_image.assert_called_once_with({"base64": "resized-bytes"})
    assert [call.args[0] for call in client.delete_image.call_args_list] == ["resized", "uploaded"]
    assert result == {
        "source_key": "receipts/test.png",
        "source_image_id": "uploaded",
        "variant": client.compress_image.return_value,
    }


@pytest.mark.parametrize("failed_step", ["resize_image", "compress_image"])
def test_variant_cleans_intermediates_on_failure(monkeypatch, failed_step):
    client = Mock()
    client.download_url.return_value = {"url": "https://storage.example/signed"}
    client.upload_image.return_value = {"image_id": "uploaded"}
    client.resize_image.return_value = {"image_id": "resized", "url": "data:image/webp;base64,bytes"}
    getattr(client, failed_step).side_effect = RuntimeError("processing failed")
    monkeypatch.setattr("src.nonprofit_media.requests.get", Mock(return_value=Mock(content=b"image")))

    with pytest.raises(RuntimeError, match="processing failed"):
        ReceiptMediaWorkflow(client, "receipts").build_variant(
            VariantRequest(key="test.png", width=120, height=90)
        )

    expected = ["uploaded"] if failed_step == "resize_image" else ["resized", "uploaded"]
    assert [call.args[0] for call in client.delete_image.call_args_list] == expected
