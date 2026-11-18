"""Run with: uvicorn src.receipt_media_service:app --reload"""

from fastapi import FastAPI, HTTPException

from src.nonprofit_media import (
    CampaignReport,
    InfraiError,
    ReceiptUploadRequest,
    VariantRequest,
    campaign_status,
    workflow_from_environment,
)

app = FastAPI(title="Nonprofit receipt media")


@app.get("/receipt-objects")
def receipt_objects() -> dict:
    try:
        workflow = workflow_from_environment()
        return workflow.client.list_objects(workflow.bucket)
    except InfraiError as error:
        raise to_http_error(error) from error


@app.delete("/receipt-object/{key:path}")
def delete_receipt_object(key: str) -> dict:
    try:
        workflow = workflow_from_environment()
        return workflow.client.delete_object(workflow.bucket, key)
    except InfraiError as error:
        raise to_http_error(error) from error


@app.delete("/receipt-bucket")
def delete_receipt_bucket() -> dict:
    try:
        workflow = workflow_from_environment()
        return workflow.client.delete_bucket(workflow.bucket)
    except InfraiError as error:
        raise to_http_error(error) from error


def to_http_error(error: InfraiError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.error)


@app.post("/receipt-upload")
def receipt_upload(request: ReceiptUploadRequest) -> dict:
    try:
        return workflow_from_environment().prepare_upload(request)
    except InfraiError as error:
        raise to_http_error(error) from error


@app.post("/receipt-variant")
def receipt_variant(request: VariantRequest) -> dict:
    try:
        return workflow_from_environment().build_variant(request)
    except InfraiError as error:
        raise to_http_error(error) from error


@app.post("/campaign-report")
def report_campaign(report: CampaignReport) -> dict:
    return {"campaign": report.campaign, "status": campaign_status(report)}
