"""RBAC roles, permissions and helpers.

Kept as a plain module so both `server.py` and the new modular routes can
reuse the exact same rules without duplication.
"""
from typing import List, Optional

ROLES = ["Admin", "Director", "ProjectManager", "Designer",
         "Accountant", "HR", "Employee", "Client"]

ROLE_PERMISSIONS = {
    "Admin": ["*.*"],
    "Director": [
        "leads.*", "projects.*", "tasks.*", "clients.*",
        "files.*", "invoices.*", "quotations.*",
        "employees.*",
        "users.read", "users.update",
        "dashboard.read", "ai.use", "rbac.read",
    ],
    "ProjectManager": [
        "leads.*", "projects.*", "tasks.*",
        "clients.read", "clients.create", "clients.update",
        "files.*", "invoices.read",
        "quotations.read", "quotations.create", "quotations.update",
        "employees.read",
        "users.read", "dashboard.read", "ai.use",
    ],
    "Designer": [
        "projects.read", "projects.update",
        "tasks.read", "tasks.create", "tasks.update",
        "files.*",
        "quotations.read", "quotations.create", "quotations.update",
        "clients.read", "leads.read",
        "employees.read",
        "dashboard.read", "ai.use",
    ],
    "Accountant": [
        "invoices.*", "quotations.*",
        "clients.read", "projects.read", "leads.read",
        "files.read", "dashboard.read", "ai.use",
        "employees.read",
    ],
    "HR": [
        "users.read", "users.update",
        "employees.*",
        "dashboard.read", "ai.use",
    ],
    "Employee": [
        "projects.read", "tasks.read", "tasks.update",
        "clients.read", "leads.read",
        "files.read", "files.create",
        "dashboard.read", "ai.use",
    ],
    "Client": [],
}

_LEGACY_ROLE_MAP = {
    "admin": "Admin",
    "employee": "Employee",
    "manager": "ProjectManager",
    "designer": "Designer",
    "accountant": "Accountant",
    "hr": "HR",
    "director": "Director",
    "owner": "Director",
    "client": "Client",
}


def normalize_role(role: Optional[str]) -> str:
    if not role:
        return "Employee"
    if role in ROLES:
        return role
    return _LEGACY_ROLE_MAP.get(role.lower(), "Employee")


def expand_permissions(role: str) -> List[str]:
    return list(ROLE_PERMISSIONS.get(normalize_role(role), []))


def has_permission(user: dict, perm: str) -> bool:
    if not user:
        return False
    role = normalize_role(user.get("role"))
    grants = ROLE_PERMISSIONS.get(role, [])
    if not grants:
        return False
    if "*.*" in grants:
        return True
    if perm in grants:
        return True
    resource = perm.split(".", 1)[0] if "." in perm else perm
    return f"{resource}.*" in grants


def user_with_perms(user: dict) -> dict:
    if not user:
        return user
    out = dict(user)
    out["role"] = normalize_role(user.get("role"))
    out["permissions"] = expand_permissions(out["role"])
    return out
