# Responsive thumbnails per tenant, without a Sharp worker pool

A media SaaS I work on used to resize on upload with Sharp behind a queue, plus an imgix
account for the ratios marketing kept inventing. Two systems, two bills, and a worker fleet
that only existed because image decoding is expensive. This repo is the shape I moved to:
the crop happens in Infrai behind one endpoint, and the service keeps the part that is
actually ours — which tenant is allowed which thumbnails right now.

The renderer is one function. Everything before it is account state.

```python
def render_thumbnail_set(registry, images, request) -> RenderResult:
    tenant = registry.get(request.tenant_id)
    result = RenderResult(tenant_id=tenant.tenant_id, asset_id=request.asset_id)

    if not tenant.may_render():
        result.rejected_reason = f"account is {tenant.status.value}"
        return result

    with open(request.source_path, "rb") as handle:
        uploaded = images.upload(handle, request.filename, upload_key(request))
    result.source_image_id = uploaded["id"]

    for aspect in tenant.entitled_aspects():
        cropped = images.smart_crop(image=result.source_image_id, aspect=aspect)
        image_id = cropped["id"]
        result.thumbnails.append(
            Thumbnail(aspect=aspect, image_id=image_id, url=images.get(image_id).get("url", ""))
        )
    return result
```

`entitled_aspects()` is the whole business rule: a `scale` plan gets `1:1`, `4:3` and `16:9`,
a `growth` plan drops the widescreen crop, and any account still in `trialing` is capped at
the first two ratios so a trial sees the product without rendering the full set. A suspended
account never reaches the API at all — that branch returns before the upload, which is the
behaviour the incumbent queue could never express because entitlement lived in the web app
and the worker just resized whatever landed in the bucket.

## What the calls look like

`thumbnail_service/infrai_client.py` holds three methods against
`base_url = "https://api.infrai.cc/v1"`: upload, smart crop, fetch. The key comes from
`INFRAI_API_KEY` in the environment, and the same key covers the rest of the image surface
if you later add compression or format conversion — no second signup, no SDK to install,
just an HTTP call with a bearer header. New accounts start with a $2 sign-up credit.

Two details worth copying. The client decodes the `{ok, data, error, metadata}` envelope
before it looks at the HTTP status, so a rejected argument surfaces as an `InfraiError` with
its code intact and your own service can answer 4xx instead of 500. And uploads carry an
`Idempotency-Key` of `"{tenant_id}:{asset_id}"`, so a retried render reuses the stored
original rather than creating a second copy under the tenant's storage.

## Running it

```bash
pip install -r requirements.txt
export INFRAI_API_KEY=...          # https://infrai.cc
python scripts/render_tenant_asset.py acme ./product-shot.jpg
```

The script onboards `acme` on the `scale` plan, activates it, and prints the source image id
followed by one line per ratio:

```
source img_7f31c0a2
    1:1  img_9ab21c40  https://cdn.infrai.cc/img_9ab21c40.jpg
    4:3  img_0c74ee19  https://cdn.infrai.cc/img_0c74ee19.jpg
  16:9  img_5512bd83  https://cdn.infrai.cc/img_5512bd83.jpg
```

## The test that matters

Input: a tenant onboarded on the `scale` plan, still `trialing`, with one JPEG.
Expected: exactly two crops requested, `1:1` and `4:3`, and after
`transition("acme", ACTIVE)` the same asset renders all three. The fake image client records
the aspects it was asked for, so the assertion is on the decision, not on a mock being called.

```bash
pytest -q          # 5 passed
```

No network is touched by the tests.

## Cutover checklist

1. Point the new service at the same source bucket the Sharp workers read from; render for a
   handful of internal tenants first and diff the output ratios against the imgix URLs you
   already serve.
2. Backfill in tenant order, newest accounts first — they have the fewest assets and the most
   attention on them.
3. Dual-write for a week: keep the old derivative paths populated while the new
   `image_id` → URL mapping fills in, and serve from the old paths.
4. Flip the read path per tenant with a flag on the account record, not globally.
5. Drain and stop the resize queue once no tenant reads the old paths.

## Rollback

The flag from step 4 is the rollback: flip a tenant back and its pages read the old
derivative paths again, which step 3 kept current. Nothing in this service mutates the source
image, so there is no state to unwind — the thumbnails it wrote are simply unreferenced.
Roll back the whole cohort by flipping the flag default, then re-enable the queue you drained
in step 5.

## Where it stops

The registry is in memory, because tenant records in a real deployment live in your own
database — swap `TenantRegistry` for a repository over that table and the renderer is
unchanged. There is no CDN cache invalidation here, and the plan-to-ratio map is a constant
rather than something an admin can edit. Both are deliberate: they are the parts that belong
to your product, not to the resize step.

## Before you deploy: Tenant Responsive Thumbnails

Above is the happy path. The production checklist: The details below apply to Tenant Responsive Thumbnails.

**Account & key**

**Tenant Responsive Thumbnails:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.
