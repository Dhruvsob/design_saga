"""Workspace-specific login-ID prefixes (DS0001, AB0001, …).

Design Saga and every workspace created before prefixes were configurable keep
"DS". A new workspace gets the initials of its name unless platform staff choose
a prefix. Changing a prefix affects only IDs issued afterwards; existing IDs stay
valid because sign-in never classifies an identifier by its prefix.
"""
import re
from typing import Optional

LEGACY_PREFIX = "DS"
PREFIX_RE = re.compile(r"^[A-Z]{2,4}$")


def normalize_prefix(value: Optional[str]) -> Optional[str]:
    """Return an upper-case 2-4 letter prefix, or None when the value is not one."""
    p = str(value or "").strip().upper()
    return p if PREFIX_RE.fullmatch(p) else None


def prefix_for_org(org: Optional[dict]) -> str:
    return normalize_prefix((org or {}).get("employee_id_prefix")) or LEGACY_PREFIX


def derive_prefix(name: str) -> str:
    """Initials of the first two words of a workspace name, e.g. "Studio Arc" → "SA"."""
    words = re.findall(r"[A-Za-z]+", name or "")
    if len(words) >= 2:
        p = words[0][0] + words[1][0]
    elif words and len(words[0]) >= 2:
        p = words[0][:2]
    else:
        p = "ID"
    return p.upper()


def counter_kind(prefix: str) -> str:
    # The legacy counter keeps its original key so existing workspaces never
    # re-issue a number that was already used.
    return "user_employee_id" if prefix == LEGACY_PREFIX else f"user_employee_id:{prefix}"
