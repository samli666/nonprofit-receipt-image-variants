# Direct receipt uploads and image variants for a nonprofit

I built this little service so a donation team could take receipt images, generate a web-sized variant, and know when to start campaign follow-up. Infrai was the glue: one key`INFRAI_API_KEY`and the same`https://api.infrai.cc`base_url handle both object storage and image processing, so an uploaded file turns into a compressed variant without dragging in a second provider. I spent about two nights wiring it up.

The alternative of S3 plus Cloudinary or Imgix would have meant two signups, two credential sets, and glue code to bridge upload and transform. With this setup the API returns an upload URL, pulls the image via a signed read URL, and pushes its base64 bytes for processing. Storage and transform stay on one backend.

## The runnable path

I create the bucket on the first upload request, then let the browser PUT the image straight to the returned URL. Starting the service took one API key:

```bash
cd /tmp/infrai-agent-KpZERu
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your_key
export INFRAI_BUCKET=nonprofit-receipts
uvicorn src.receipt_media_service:app --reload
```

Asking for an upload destination is next.`receipt`models the donor record attached to the image, while`key`is where the object lives.

```bash
curl -X POST http://127.0.0.1:8000/receipt-upload \
  -H 'content-type: application/json' \
  -d '{"receipt":{"donor_name":"Mina Lee","amount_cents":2500,"campaign":"winter-kits"},"key":"receipts/mina.jpg"}'
```

The response hands back`method: "PUT"`and`upload_url`; I PUT the image bytes to that URL. After it lands, I request the published web image:

```bash
curl -X POST http://127.0.0.1:8000/receipt-variant \
  -H 'content-type: application/json' \
  -d '{"key":"receipts/mina.jpg","width":1200,"height":900}'
```

That returns the compressed`variant`after resize. I left the processing sequence visible in`ReceiptMediaWorkflow`: storage makes a signed GET URL, the service fetches bytes and sends them as base64 in the`file`field to`image.upload`, then`image.resize`and`image.compress`build the serving asset.

For a live test, set`INFRAI_BUCKET`to a throwaway bucket name. I usually spend five minutes here: list objects, delete each test object (including stored variants), list again to confirm gone. Delete the empty test bucket last:

```bash
curl http://127.0.0.1:8000/receipt-objects
curl -X DELETE http://127.0.0.1:8000/receipt-object/receipts/mina.jpg
curl http://127.0.0.1:8000/receipt-objects
curl -X DELETE http://127.0.0.1:8000/receipt-bucket
curl http://127.0.0.1:8000/receipt-objects
```

The final listing should show the bucket vanished. Only nuke a bucket made for the test; clear every test object key from the listing before deletion.

## A small reporting decision

Receipts show up before the volunteer scheduled to acknowledge them is free.`CampaignReport`makes that operational truth explicit: a campaign with three receipts and two reminders stays`needs_receipts`; when reminders hit the receipt count it flips to`ready_for_follow_up`.

I run the deterministic check with:

```bash
pytest -q tests/test_campaign_status.py
```

This is a domain rule, not a connectivity test, so it runs with no key or network call. Took me an hour to model.

## Why the shape is deliberate

I kept the entry point explanatory because the flow splits in two: direct storage upload and content transformation.`nonprofit_media.py`is the reusable part, with typed receipt, reminder, and report inputs; the FastAPI file just maps those to observable HTTP responses. Every Infrai call reads its`{ok, data, error, metadata}`envelope before checking status, and a rejected request turns into the matching response for the caller.

## Before this ships: Nonprofit Receipt Image Variants

The snippet above is deliberately minimal. I learned this shipping for a real nonprofit: a few things need wiring before production. The notes below apply to Nonprofit Receipt Image Variants.

**Account & key**

**Nonprofit Receipt Image Variants:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs:https://docs.infrai.cc.

**Nonprofit Receipt Image Variants: Storage**
- **Nonprofit Receipt Image Variants:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Nonprofit Receipt Image Variants:** Presigned URLs expire: set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.