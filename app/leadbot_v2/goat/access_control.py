from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    PRESIDENT = "president"
    VICE_PRESIDENT = "vice_president"
    SALES = "sales"
    MARKETING = "marketing"
    PROJECT_MANAGER = "project_manager"
    FIELD = "field"
    CLIENT = "client"


class Permission(str, Enum):
    CRM_READ = "crm.read"
    CRM_WRITE = "crm.write"

    PROJECT_READ = "project.read"
    PROJECT_WRITE = "project.write"

    CLIENT_PORTAL = "client.portal"

    COMMUNICATIONS = "communications.use"

    SALES = "sales.manage"
    MARKETING = "marketing.manage"

    MATERIALS_READ = "materials.read"
    MATERIALS_WRITE = "materials.write"

    FINANCIAL_READ = "financial.read"
    FINANCIAL_WRITE = "financial.write"

    ANALYTICS_READ = "analytics.read"
    EXECUTIVE_INTELLIGENCE = "executive_intelligence.use"

    USER_ADMIN = "users.admin"
    SECURITY_ADMIN = "security.admin"
    SYSTEM_ADMIN = "system.admin"


EXECUTIVE_ROLES = frozenset({
    Role.PRESIDENT,
    Role.VICE_PRESIDENT,
})


ROLE_PERMISSIONS = {
    Role.PRESIDENT: frozenset(Permission),
    Role.VICE_PRESIDENT: frozenset(Permission),

    Role.SALES: frozenset({
        Permission.CRM_READ,
        Permission.CRM_WRITE,
        Permission.PROJECT_READ,
        Permission.COMMUNICATIONS,
        Permission.SALES,
        Permission.ANALYTICS_READ,
    }),

    Role.MARKETING: frozenset({
        Permission.CRM_READ,
        Permission.CRM_WRITE,
        Permission.COMMUNICATIONS,
        Permission.MARKETING,
        Permission.ANALYTICS_READ,
    }),

    Role.PROJECT_MANAGER: frozenset({
        Permission.CRM_READ,
        Permission.PROJECT_READ,
        Permission.PROJECT_WRITE,
        Permission.CLIENT_PORTAL,
        Permission.COMMUNICATIONS,
        Permission.MATERIALS_READ,
        Permission.MATERIALS_WRITE,
    }),

    Role.FIELD: frozenset({
        Permission.PROJECT_READ,
        Permission.COMMUNICATIONS,
        Permission.MATERIALS_READ,
        Permission.MATERIALS_WRITE,
    }),

    Role.CLIENT: frozenset({
        Permission.PROJECT_READ,
        Permission.CLIENT_PORTAL,
        Permission.COMMUNICATIONS,
    }),
}


FINANCIAL_PERMISSIONS = frozenset({
    Permission.FINANCIAL_READ,
    Permission.FINANCIAL_WRITE,
})


@dataclass(frozen=True)
class Principal:
    user_id: str
    tenant_id: str
    role: Role
    email: str | None = None
    business_units: tuple[str, ...] = ()
    assigned_projects: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResourceContext:
    tenant_id: str
    business_unit: str | None = None
    project_id: str | None = None


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    permission: Permission


class AccessDenied(PermissionError):
    pass


class AuthorizationEngine:
    """
    Zero-trust, default-deny authorization core.

    Authentication proves identity.
    This engine independently determines what that identity may do.
    """

    def authorize(
        self,
        principal: Principal,
        permission: Permission,
        resource: ResourceContext,
    ) -> AuthorizationDecision:

        # Tenant boundary is absolute.
        if principal.tenant_id != resource.tenant_id:
            return AuthorizationDecision(
                False,
                "cross-tenant access denied",
                permission,
            )

        granted = ROLE_PERMISSIONS.get(principal.role, frozenset())

        if permission not in granted:
            return AuthorizationDecision(
                False,
                "permission not granted to role",
                permission,
            )

        # Financial information is restricted to executives.
        if (
            permission in FINANCIAL_PERMISSIONS
            and principal.role not in EXECUTIVE_ROLES
        ):
            return AuthorizationDecision(
                False,
                "financial access restricted to executives",
                permission,
            )

        # Executives have organization-wide authority after tenant check.
        if principal.role in EXECUTIVE_ROLES:
            return AuthorizationDecision(
                True,
                "executive authorization",
                permission,
            )

        # Business-unit isolation.
        if (
            resource.business_unit
            and principal.business_units
            and resource.business_unit not in principal.business_units
        ):
            return AuthorizationDecision(
                False,
                "business-unit access denied",
                permission,
            )

        # PM, field and client project access is assignment scoped.
        if (
            permission in {
                Permission.PROJECT_READ,
                Permission.PROJECT_WRITE,
                Permission.CLIENT_PORTAL,
            }
            and principal.role in {
                Role.PROJECT_MANAGER,
                Role.FIELD,
                Role.CLIENT,
            }
        ):
            if not resource.project_id:
                return AuthorizationDecision(
                    False,
                    "project context required",
                    permission,
                )

            if resource.project_id not in principal.assigned_projects:
                return AuthorizationDecision(
                    False,
                    "project not assigned to principal",
                    permission,
                )

        return AuthorizationDecision(
            True,
            "authorized",
            permission,
        )

    def require(
        self,
        principal: Principal,
        permission: Permission,
        resource: ResourceContext,
    ) -> None:
        decision = self.authorize(
            principal,
            permission,
            resource,
        )

        if not decision.allowed:
            raise AccessDenied(decision.reason)
