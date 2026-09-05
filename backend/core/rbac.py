"""RBAC roles, permissions and helpers.

Kept as a plain module so both `server.py` and the new modular routes can
reuse the exact same rules without duplication.
"""
from typing import List, Optional

ROLES = ["SuperAdmin", "Admin", "Director", "ProjectManager", "Designer",
         "Accountant", "HR", "Employee", "Client"]

ROLE_PERMISSIONS = {
    # Platform-level god role. Cross-org. Manages tenants + platform config.
    "SuperAdmin": ["*.*", "platform.*"],
    "Admin": ["*.*"],
    "Director": [
        "leads.*", "projects.*", "tasks.*", "clients.*",
        "files.*", "invoices.*", "quotations.*",
        "employees.*",
        "finance.*", "payroll.*",
        "vendors.*",                          # full vendor management + finance
        "users.read", "users.update",
        "dashboard.read", "ai.use", "rbac.read",
    ],
    "ProjectManager": [
        "leads.*", "projects.*", "tasks.*",
        "clients.read", "clients.create", "clients.update",
        "files.*", "invoices.read",
        "quotations.read", "quotations.create", "quotations.update",
        "employees.read",
        "vendors.read", "vendors.create", "vendors.update",   # assign vendors, no bills/payments
        "users.read", "dashboard.read", "ai.use",
    ],
    "Designer": [
        "projects.read", "projects.update",
        "tasks.read", "tasks.create", "tasks.update",
        "files.*",
        "quotations.read", "quotations.create", "quotations.update",
        "clients.read", "leads.read",
        "employees.read",
        "vendors.read",                       # read-only for task assignment
        "dashboard.read", "ai.use",
    ],
    "Accountant": [
        "invoices.*", "quotations.*",
        "clients.read", "projects.read", "leads.read",
        "files.read", "dashboard.read", "ai.use",
        "employees.read",
        "finance.*", "payroll.*",
        "vendors.*",                          # bills, payments, ledger
    ],
    "HR": [
        "users.read", "users.update",
        "employees.*",
        "payroll.read", "payroll.create",     # limited — cannot see full accounting
        "dashboard.read", "ai.use",
    ],
    "Employee": [
        "projects.read", "tasks.read", "tasks.update",
        "clients.read", "leads.read",
        "files.read", "files.create",
        "vendors.read",                       # read-only lookup for tasks
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
    "superadmin": "SuperAdmin",
    "super_admin": "SuperAdmin",
    "platform_admin": "SuperAdmin",
}
# Public alias — imported by server.py so it doesn't duplicate the map.
LEGACY_ROLE_MAP = _LEGACY_ROLE_MAP


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
    # Prefer permissions already resolved onto the user (these reflect any
    # per-tenant role overrides attached at request time). Fall back to the
    # static role defaults when nothing is attached.
    grants = user.get("permissions")
    if not (isinstance(grants, list) and grants):
        grants = ROLE_PERMISSIONS.get(role, [])
    if not grants:
        return False
    if "*.*" in grants:
        return True
    if perm in grants:
        return True
    resource = perm.split(".", 1)[0] if "." in perm else perm
    return f"{resource}.*" in grants


# ------------------------------------------------------------------
# Editable-permission catalogue — drives the Team & Roles matrix UI.
# Each module lists the granular actions an Admin can grant/revoke per role.
# ------------------------------------------------------------------
PERMISSION_CATALOG = {
    "modules": [
        {"key": "dashboard",  "label": "Dashboard",        "actions": ["read"]},
        {"key": "leads",      "label": "Leads / CRM",      "actions": ["read", "create", "update", "delete"]},
        {"key": "projects",   "label": "Projects",         "actions": ["read", "create", "update", "delete"]},
        {"key": "tasks",      "label": "Tasks",            "actions": ["read", "create", "update", "delete"]},
        {"key": "clients",    "label": "Clients",          "actions": ["read", "create", "update", "delete"]},
        {"key": "files",      "label": "Files / Drawings", "actions": ["read", "create", "update", "delete"]},
        {"key": "quotations", "label": "Quotations",       "actions": ["read", "create", "update", "delete"]},
        {"key": "invoices",   "label": "Invoices",         "actions": ["read", "create", "update", "delete"]},
        {"key": "finance",    "label": "Accounting",       "actions": ["read", "create", "update", "delete"]},
        {"key": "vendors",    "label": "Vendors",          "actions": ["read", "create", "update", "delete"]},
        {"key": "employees",  "label": "Employees",        "actions": ["read", "create", "update", "delete"]},
        {"key": "payroll",    "label": "Payroll",          "actions": ["read", "create", "update", "delete"]},
        {"key": "users",      "label": "Team / Users",     "actions": ["read", "update"]},
        {"key": "ai",         "label": "AI Assistant",     "actions": ["use"]},
    ],
}
ACTION_LABELS = {"read": "View", "create": "Create", "update": "Edit",
                 "delete": "Delete", "use": "Use"}

# Roles whose permissions are locked (cannot be edited via the matrix).
PROTECTED_ROLES = {"SuperAdmin", "Admin"}


def valid_permission_keys() -> set:
    """All permission strings the matrix may legitimately set."""
    keys = set()
    for m in PERMISSION_CATALOG["modules"]:
        keys.add(f"{m['key']}.*")
        for a in m["actions"]:
            keys.add(f"{m['key']}.{a}")
    return keys


def user_with_perms(user: dict) -> dict:
    if not user:
        return user
    out = {k: v for k, v in user.items() if k != "password_hash"}
    out["role"] = normalize_role(user.get("role"))
    out["permissions"] = expand_permissions(out["role"])
    return out
