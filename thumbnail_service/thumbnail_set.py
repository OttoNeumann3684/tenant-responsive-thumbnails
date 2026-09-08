"""Render the responsive thumbnail set a tenant is entitled to."""

from __future__ import annotations

from .infrai_client import InfraiImages
from .models import RenderResult, Thumbnail, ThumbnailRequest
from .tenant_registry import TenantRegistry


def upload_key(request: ThumbnailRequest) -> str:
    """Stable per-asset key so a replayed render reuses the same upload."""
    return f"{request.tenant_id}:{request.asset_id}"


def render_thumbnail_set(
    registry: TenantRegistry, images: InfraiImages, request: ThumbnailRequest
) -> RenderResult:
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
