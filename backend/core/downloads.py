"""Safe HTTP download header helpers."""

import re
import unicodedata
from urllib.parse import quote


_CONTROL_OR_PATH = re.compile(r"[\x00-\x1f\x7f/\\\\]+")
_UNSAFE_ASCII = re.compile(r"[^A-Za-z0-9._ -]+")


def _clean_name(value: object, fallback: str) -> str:
    name = _CONTROL_OR_PATH.sub("_", str(value or "")).strip(" .")
    name = name.replace('"', "_").replace(";", "_")
    return name[:180] or fallback


def content_disposition(disposition: str, filename: object,
                        fallback: str = "download") -> str:
    """Build a CRLF/path-safe header with an RFC 5987 Unicode filename."""
    kind = disposition if disposition in {"inline", "attachment"} else "attachment"
    clean = _clean_name(filename, fallback)
    ascii_name = unicodedata.normalize("NFKD", clean).encode("ascii", "ignore").decode()
    ascii_name = _UNSAFE_ASCII.sub("_", ascii_name).strip(" .")[:180] or fallback
    encoded = quote(clean, safe="!#$&+-.^_`|~")
    return f'{kind}; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'
