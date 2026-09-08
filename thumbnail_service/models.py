"""Typed request/state models for the thumbnail service."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class AccountStatus(str, Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class Plan(str, Enum):
    STARTER = "starter"
    GROWTH = "growth"
    SCALE = "scale"


# Which crop ratios each plan is entitled to render, in render order.
PLAN_ASPECTS: dict[Plan, tuple[str, ...]] = {
    Plan.STARTER: ("1:1",),
    Plan.GROWTH: ("1:1", "4:3"),
    Plan.SCALE: ("1:1", "4:3", "16:9"),
}

# A trial gets the shape of the product, capped to two ratios.
TRIAL_ASPECT_CAP = 2


@dataclass(frozen=True)
class Tenant:
    tenant_id: str
    name: str
    plan: Plan
    status: AccountStatus

    def entitled_aspects(self) -> tuple[str, ...]:
        aspects = PLAN_ASPECTS[self.plan]
        if self.status is AccountStatus.TRIALING:
            return aspects[:TRIAL_ASPECT_CAP]
        return aspects

    def may_render(self) -> bool:
        return self.status in (AccountStatus.TRIALING, AccountStatus.ACTIVE)


@dataclass(frozen=True)
class ThumbnailRequest:
    """One asset a tenant wants a responsive thumbnail set for."""

    tenant_id: str
    asset_id: str
    source_path: str
    filename: str


@dataclass(frozen=True)
class Thumbnail:
    aspect: str
    image_id: str
    url: str


@dataclass
class RenderResult:
    tenant_id: str
    asset_id: str
    source_image_id: str = ""
    thumbnails: list[Thumbnail] = field(default_factory=list)
    rejected_reason: str = ""

    @property
    def rendered(self) -> bool:
        return not self.rejected_reason

    def aspects(self) -> Sequence[str]:
        return [t.aspect for t in self.thumbnails]
