from dataclasses import dataclass
from typing import Iterable

import jwt

from .config import get_settings
from .security import verify_password
from .tenancy import TenantContext


@dataclass(frozen=True)
class Principal:
    username: str
    role: str
    tenant_id: str = "default"
    org_id: str = "default-org"
    department_id: str = "peopleops"

    def scope(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "org_id": self.org_id,
            "department_id": self.department_id,
        }


ROLE_PERMISSIONS = {
    "admin": {"chat", "resume", "rag", "tool", "audit", "users"},
    "hrbp": {"chat", "resume", "rag", "tool"},
    "viewer": {"chat", "rag"},
}


def authenticate_with_password(password: str) -> Principal | None:
    settings = get_settings()
    if verify_password(password, settings.access_password):
        return Principal(username="local-admin", role="admin")
    return None


def authenticate_with_oidc(token: str) -> Principal | None:
    settings = get_settings()
    if not settings.oidc_enabled or not token:
        return None

    algorithms = ["RS256"]
    key = None
    if settings.oidc_hs256_secret:
        algorithms = ["HS256"]
        key = settings.oidc_hs256_secret
    elif settings.oidc_jwks_url:
        key = jwt.PyJWKClient(settings.oidc_jwks_url).get_signing_key_from_jwt(token).key
    else:
        raise RuntimeError("OIDC_JWKS_URL or OIDC_HS256_SECRET is required when OIDC is enabled.")

    payload = jwt.decode(
        token,
        key=key,
        algorithms=algorithms,
        audience=settings.oidc_audience,
        issuer=settings.oidc_issuer,
        options={
            "verify_aud": bool(settings.oidc_audience),
            "verify_iss": bool(settings.oidc_issuer),
        },
    )
    username = str(payload.get("preferred_username") or payload.get("email") or payload.get("sub") or "").strip()
    role_value = payload.get(settings.oidc_role_claim, settings.oidc_default_role)
    if isinstance(role_value, list):
        role = next((str(item).lower() for item in role_value if str(item).lower() in ROLE_PERMISSIONS), settings.oidc_default_role)
    else:
        role = str(role_value or settings.oidc_default_role).lower()
    if not username:
        return None
    if role not in ROLE_PERMISSIONS:
        role = settings.oidc_default_role if settings.oidc_default_role in ROLE_PERMISSIONS else "viewer"
    scope = TenantContext.from_headers(
        tenant_id=_claim_value(payload, "tenant_id"),
        org_id=_claim_value(payload, "org_id"),
        department_id=_claim_value(payload, "department_id"),
        default_tenant_id=settings.default_tenant_id,
        default_org_id=settings.default_org_id,
        default_department_id=settings.default_department_id,
    )
    return Principal(username=username, role=role, **scope.as_dict())


def _claim_value(payload: dict, name: str) -> str | None:
    value = payload.get(name)
    return value if isinstance(value, str) else None


def has_permission(principal: Principal, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(principal.role, set())


def require_permission(principal: Principal, permission: str) -> None:
    if not has_permission(principal, permission):
        raise PermissionError(f"User {principal.username} lacks permission: {permission}")


def allowed_permissions(role: str) -> Iterable[str]:
    return sorted(ROLE_PERMISSIONS.get(role, set()))
