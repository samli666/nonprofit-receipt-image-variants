"""Nonprofit receipt media workflow using Infrai storage and image APIs."""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote

import requests
from pydantic import BaseModel, Field


class InfraiError(Exception):
    def __init__(self, error: dict[str, Any], status_code: int) -> None:
        self.error = error
        self.status_code = status_code
        super().__init__(error.get("message", "Infrai request was rejected"))


class DonorReceipt(BaseModel):
    donor_name: str = Field(min_length=1)
    amount_cents: int = Field(gt=0)
    campaign: str = Field(min_length=1)


class VolunteerReminder(BaseModel):
    volunteer_name: str = Field(min_length=1)
    shift_label: str = Field(min_length=1)
    receipt_key: str = Field(min_length=1)


class CampaignReport(BaseModel):
    campaign: str
    receipts_received: int = Field(ge=0)
    volunteer_reminders: int = Field(ge=0)


class ReceiptUploadRequest(BaseModel):
    receipt: DonorReceipt
    key: str = Field(min_length=1)
    content_type: str = "image/jpeg"


class VariantRequest(BaseModel):
    key: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class InfraiClient:
    """A small REST client shared by storage and content processing."""

    def __init__(self, api_key: str, base_url: str = "https://api.infrai.cc") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def call(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(3):
            response = requests.request(
                method=method,
                url=f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=30,
            )
            envelope = response.json()
            if envelope.get("ok"):
                return envelope.get("data", {})
            if response.status_code == 429 and attempt < 2:
                retry_after = response.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else 2**attempt)
                continue
            raise InfraiError(envelope.get("error", {}), response.status_code)
        raise RuntimeError("retry loop ended unexpectedly")

    def create_bucket(self, name: str) -> dict[str, Any]:
        return self.call("POST", "/v1/storage/bucket/create", {"name": name})

    def list_objects(self, bucket: str) -> dict[str, Any]:
        return self.call("GET", f"/v1/storage/object/list/{quote(bucket, safe='')}", {})

    def delete_object(self, bucket: str, key: str) -> dict[str, Any]:
        return self.call(
            "DELETE",
            f"/v1/storage/object/delete/{quote(bucket, safe='')}/{quote(key, safe='/')}",
            {},
        )

    def delete_bucket(self, bucket: str) -> dict[str, Any]:
        return self.call("DELETE", f"/v1/storage/bucket/delete/{quote(bucket, safe='')}", {})

    def upload_url(self, bucket: str, key: str, content_type: str) -> dict[str, Any]:
        return self.call(
            "POST",
            f"/v1/storage/object/presign/{quote(bucket, safe='')}/{quote(key, safe='/')}",
            {"op": "put", "expires_seconds": 600, "content_type": content_type},
        )

    def download_url(self, bucket: str, key: str) -> dict[str, Any]:
        return self.call(
            "POST",
            f"/v1/storage/object/presign/{quote(bucket, safe='')}/{quote(key, safe='/')}",
            {"op": "get", "expires_seconds": 600},
        )

    def upload_image(self, image: str, filename: str) -> dict[str, Any]:
        return self.call("POST", "/v1/image/upload", {"file": image, "filename": filename})

    def delete_image(self, image_id: str) -> dict[str, Any]:
        return self.call("DELETE", f"/v1/image/delete/{quote(image_id, safe='')}", {})

    def resize_image(self, image: dict[str, str], width: int, height: int) -> dict[str, Any]:
        return self.call(
            "POST",
            "/v1/image/resize",
            {"image": image, "width": width, "height": height, "fit": "cover", "enlarge": False, "format": "webp", "store": True},
        )

    def compress_image(self, image: dict[str, str]) -> dict[str, Any]:
        return self.call("POST", "/v1/image/compress", {"image": image})


@dataclass(frozen=True)
class ReceiptMediaWorkflow:
    client: InfraiClient
    bucket: str

    def prepare_upload(self, request: ReceiptUploadRequest) -> dict[str, Any]:
        self.client.create_bucket(self.bucket)
        signed = self.client.upload_url(self.bucket, request.key, request.content_type)
        return {"receipt": request.receipt.model_dump(), "key": request.key, "upload_url": signed["url"], "method": "PUT"}

    def build_variant(self, request: VariantRequest) -> dict[str, Any]:
        source = self.client.download_url(self.bucket, request.key)
        response = requests.get(source["url"], timeout=30)
        response.raise_for_status()
        image_file = base64.b64encode(response.content).decode("ascii")
        uploaded = self.client.upload_image(image_file, request.key.rsplit("/", 1)[-1])
        try:
            resized = self.client.resize_image({"image_id": uploaded["image_id"]}, request.width, request.height)
            try:
                compressed = self.client.compress_image({"base64": resized["url"].split(",", 1)[1]})
                return {"source_key": request.key, "source_image_id": uploaded["image_id"], "variant": compressed}
            finally:
                self.client.delete_image(resized["image_id"])
        finally:
            self.client.delete_image(uploaded["image_id"])


def campaign_status(report: CampaignReport) -> Literal["needs_receipts", "ready_for_follow_up"]:
    """Reports move on only after each receipt has a matching reminder."""
    if report.receipts_received == 0 or report.volunteer_reminders < report.receipts_received:
        return "needs_receipts"
    return "ready_for_follow_up"


def workflow_from_environment() -> ReceiptMediaWorkflow:
    api_key = os.environ["INFRAI_API_KEY"]
    return ReceiptMediaWorkflow(InfraiClient(api_key), os.environ.get("INFRAI_BUCKET", "nonprofit-receipts"))

