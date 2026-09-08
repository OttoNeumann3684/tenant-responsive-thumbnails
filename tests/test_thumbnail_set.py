from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from thumbnail_service.models import AccountStatus, Plan, ThumbnailRequest
from thumbnail_service.tenant_registry import LifecycleError, TenantRegistry
from thumbnail_service.thumbnail_set import render_thumbnail_set, upload_key


class FakeImages:
    """Records what the renderer would have asked the image API to do."""

    def __init__(self) -> None:
        self.crops: list[str] = []
        self.idempotency_keys: list[str] = []

    def upload(self, file, filename, idempotency_key):
        self.idempotency_keys.append(idempotency_key)
        return {"id": "img_src"}

    def smart_crop(self, image, aspect):
        self.crops.append(aspect)
        return {"id": f"img_{aspect.replace(':', 'x')}"}

    def get(self, image_id):
        return {"url": f"https://cdn.example.com/{image_id}.jpg"}


@pytest.fixture()
def source(tmp_path):
    path = tmp_path / "hero.jpg"
    path.write_bytes(b"jpeg-bytes")
    return path


def make_request(source, tenant_id="acme"):
    return ThumbnailRequest(
        tenant_id=tenant_id, asset_id="hero", source_path=str(source), filename="hero.jpg"
    )


def test_trial_on_scale_plan_is_capped_to_two_ratios(source):
    registry = TenantRegistry()
    registry.onboard("acme", "Acme", Plan.SCALE)
    images = FakeImages()

    result = render_thumbnail_set(registry, images, make_request(source))

    assert list(result.aspects()) == ["1:1", "4:3"]
    assert images.crops == ["1:1", "4:3"]
    assert result.thumbnails[0].url == "https://cdn.example.com/img_1x1.jpg"


def test_activation_unlocks_the_full_set(source):
    registry = TenantRegistry()
    registry.onboard("acme", "Acme", Plan.SCALE)
    registry.transition("acme", AccountStatus.ACTIVE)
    images = FakeImages()

    result = render_thumbnail_set(registry, images, make_request(source))

    assert list(result.aspects()) == ["1:1", "4:3", "16:9"]
    assert images.idempotency_keys == ["acme:hero"]


def test_suspended_account_renders_nothing(source):
    registry = TenantRegistry()
    registry.onboard("acme", "Acme", Plan.GROWTH)
    registry.transition("acme", AccountStatus.ACTIVE)
    registry.transition("acme", AccountStatus.SUSPENDED)
    images = FakeImages()

    result = render_thumbnail_set(registry, images, make_request(source))

    assert not result.rendered
    assert result.rejected_reason == "account is suspended"
    assert images.crops == []


def test_closed_accounts_are_terminal():
    registry = TenantRegistry()
    registry.onboard("acme", "Acme", Plan.STARTER)
    registry.transition("acme", AccountStatus.CLOSED)
    with pytest.raises(LifecycleError):
        registry.transition("acme", AccountStatus.ACTIVE)


def test_upload_key_is_stable_per_asset(source):
    assert upload_key(make_request(source)) == "acme:hero"
