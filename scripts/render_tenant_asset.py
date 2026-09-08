#!/usr/bin/env python3
"""Onboard a tenant, activate it, and render one asset's thumbnail set.

    python scripts/render_tenant_asset.py acme ./product-shot.jpg
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from thumbnail_service.infrai_client import InfraiError, InfraiImages  # noqa: E402
from thumbnail_service.models import AccountStatus, Plan, ThumbnailRequest  # noqa: E402
from thumbnail_service.tenant_registry import TenantRegistry  # noqa: E402
from thumbnail_service.thumbnail_set import render_thumbnail_set  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    tenant_id, source = argv[1], argv[2]

    registry = TenantRegistry()
    registry.onboard(tenant_id, name=tenant_id.title(), plan=Plan.SCALE)
    registry.transition(tenant_id, AccountStatus.ACTIVE)

    request = ThumbnailRequest(
        tenant_id=tenant_id,
        asset_id=Path(source).stem,
        source_path=source,
        filename=Path(source).name,
    )
    try:
        result = render_thumbnail_set(registry, InfraiImages(), request)
    except InfraiError as err:
        print(f"rejected by the image API ({err.status}): {err.code}")
        return 1

    if not result.rendered:
        print(f"skipped {request.asset_id}: {result.rejected_reason}")
        return 0

    print(f"source {result.source_image_id}")
    for thumb in result.thumbnails:
        print(f"  {thumb.aspect:>5}  {thumb.image_id}  {thumb.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
