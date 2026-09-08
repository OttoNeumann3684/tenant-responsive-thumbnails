"""Onboarding, lifecycle transitions and the admin operations around them."""

from __future__ import annotations

from .models import AccountStatus, Plan, Tenant

# Transitions an operator is allowed to drive from the admin console.
ALLOWED_TRANSITIONS: dict[AccountStatus, frozenset[AccountStatus]] = {
    AccountStatus.TRIALING: frozenset({AccountStatus.ACTIVE, AccountStatus.CLOSED}),
    AccountStatus.ACTIVE: frozenset({AccountStatus.SUSPENDED, AccountStatus.CLOSED}),
    AccountStatus.SUSPENDED: frozenset({AccountStatus.ACTIVE, AccountStatus.CLOSED}),
    AccountStatus.CLOSED: frozenset(),
}


class LifecycleError(RuntimeError):
    pass


class TenantRegistry:
    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}

    def onboard(self, tenant_id: str, name: str, plan: Plan) -> Tenant:
        if tenant_id in self._tenants:
            return self._tenants[tenant_id]
        tenant = Tenant(tenant_id=tenant_id, name=name, plan=plan, status=AccountStatus.TRIALING)
        self._tenants[tenant_id] = tenant
        return tenant

    def get(self, tenant_id: str) -> Tenant:
        try:
            return self._tenants[tenant_id]
        except KeyError:
            raise LifecycleError(f"unknown tenant {tenant_id}") from None

    def transition(self, tenant_id: str, target: AccountStatus) -> Tenant:
        tenant = self.get(tenant_id)
        if target not in ALLOWED_TRANSITIONS[tenant.status]:
            raise LifecycleError(f"{tenant.status.value} -> {target.value} is not a valid move")
        updated = Tenant(tenant.tenant_id, tenant.name, tenant.plan, target)
        self._tenants[tenant_id] = updated
        return updated

    def change_plan(self, tenant_id: str, plan: Plan) -> Tenant:
        tenant = self.get(tenant_id)
        if tenant.status is AccountStatus.CLOSED:
            raise LifecycleError("a closed account keeps its plan")
        updated = Tenant(tenant.tenant_id, tenant.name, plan, tenant.status)
        self._tenants[tenant_id] = updated
        return updated
