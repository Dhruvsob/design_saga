"""HTTP-layer hardening shared by every route.

* Request IDs (`X-Request-ID`) + one structured, redacted JSON access log line.
* CSRF defence-in-depth: state-changing requests that carry a browser Origin /
  Referer must come from this site or an allow-listed origin (cookies are
  already SameSite=Lax + HttpOnly + Secure).
* Per-source rate limits for expensive / abuse-prone endpoint classes
  (password resets, public portal, search, AI, exports, uploads).
* Baseline security headers on API responses.
* Audit records for data exports.

The limiter is in-process (the backend runs one uvicorn worker). If workers
are ever increased, limits become per-worker; move buckets to Redis/DB then.
"""
import hashlib
import json
import logging
import os
import re
import time
import uuid
from collections import deque
from typing import Deque, Dict, Optional, Tuple
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse

access_log = logging.getLogger("access")

# --------------------------------------------------------------------------
# Log redaction
# --------------------------------------------------------------------------
_REDACT_PATTERNS = [
    (re.compile(r"(mongodb(?:\+srv)?|postgres(?:ql)?)://[^\s/@]+@", re.I), r"\1://***@"),
    (re.compile(r"(?i)\b(password|passwd|secret|token|session_token|api[_-]?key|authorization)"
                r"(\"?\s*[:=]\s*\"?)([^\s\",&]+)"), r"\1\2***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer ***"),
    (re.compile(r"sk-[A-Za-z0-9_-]{12,}"), "sk-***"),
]


def redact(text: str) -> str:
    for pat, rep in _REDACT_PATTERNS:
        text = pat.sub(rep, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            red = redact(msg)
            if red != msg:
                record.msg, record.args = red, ()
        except Exception:  # noqa: BLE001
            pass
        return True


def install_log_redaction():
    flt = RedactingFilter()
    root = logging.getLogger()
    for h in root.handlers:
        h.addFilter(flt)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "access"):
        lg = logging.getLogger(name)
        lg.addFilter(flt)
        for h in lg.handlers:
            h.addFilter(flt)


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------
# (method or "*", path regex, bucket, limit, window seconds)
RATE_RULES = [
    ("POST", re.compile(r"^/api/auth/(login|session|password-login)"), "auth", 30, 60),
    ("*", re.compile(r"/reset-password(?:/[^/]+)?$"), "password_reset", 10, 900),
    ("POST", re.compile(r"/account/password$|/auth/change-password$"), "password_change", 10, 900),
    ("POST", re.compile(r"^/api/portal/[^/]+/message$"), "portal_write", 10, 60),
    ("*", re.compile(r"^/api/portal/"), "portal", 60, 60),
    ("*", re.compile(r"^/api/org/public/"), "public_branding", 60, 60),
    ("*", re.compile(r"^/api/search"), "search", 60, 60),
    ("*", re.compile(r"^/api/ai/|/ai-suggest$"), "ai", 15, 60),
    ("*", re.compile(r"^/api/ai/|/ai-suggest$"), "ai_daily", 200, 86400),
    ("GET", re.compile(r"(\.csv|/csv|/pdf|/export[^/]*|/payslip[^/]*)$"), "export", 30, 60),
    ("POST", re.compile(r"/logo(/upload)?$|/bank-statement|/import"), "upload", 20, 300),
]
EXPORT_RE = re.compile(r"(\.csv|/csv|/pdf|/export[^/]*|/payslip[^/]*)$")

_hits: Dict[str, Deque[float]] = {}
_MAX_KEYS = 50000


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",", 1)[0].strip()
    if not ip and request.client:
        ip = request.client.host
    return ip or "unknown"


def _h(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _credential_key(request: Request) -> Optional[str]:
    tok = request.cookies.get("session_token")
    auth = request.headers.get("authorization") or ""
    if not tok and auth.lower().startswith("bearer "):
        tok = auth[7:].strip()
    return _h(tok) if tok else None


def _check(key: str, limit: int, window: int, now: float) -> Tuple[bool, int]:
    dq = _hits.get(key)
    if dq is None:
        if len(_hits) >= _MAX_KEYS:
            # Drop the stalest ~10% to bound memory.
            for k in list(_hits.keys())[: _MAX_KEYS // 10]:
                _hits.pop(k, None)
        dq = _hits[key] = deque()
    cutoff = now - window
    while dq and dq[0] <= cutoff:
        dq.popleft()
    if len(dq) >= limit:
        retry = int(dq[0] + window - now) + 1
        return False, max(retry, 1)
    dq.append(now)
    return True, 0


def rate_limit_decision(request: Request) -> Optional[Tuple[str, int]]:
    """Return (bucket, retry_after) when the request must be refused."""
    path = request.url.path
    method = request.method.upper()
    if method == "OPTIONS":
        return None
    ip_key = _h(_client_ip(request))
    cred = _credential_key(request)
    now = time.monotonic()
    for m, rx, bucket, limit, window in RATE_RULES:
        if m != "*" and m != method:
            continue
        if not rx.search(path):
            continue
        ok, retry = _check(f"{bucket}:ip:{ip_key}", limit, window, now)
        if ok and cred:
            ok, retry = _check(f"{bucket}:cred:{cred}", limit, window, now)
        if not ok:
            return bucket, retry
    return None


def reset_rate_limits():
    _hits.clear()


# --------------------------------------------------------------------------
# Origin / CSRF
# --------------------------------------------------------------------------
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _allowed_origins() -> set:
    raw = os.environ.get("CORS_ORIGINS", "")
    return {o.strip().rstrip("/").lower() for o in raw.split(",") if o.strip() and o.strip() != "*"}


def _origin_of(url: str) -> Optional[str]:
    try:
        p = urlsplit(url)
    except ValueError:
        return None
    if not p.scheme or not p.netloc:
        return None
    return f"{p.scheme}://{p.netloc}".lower()


def csrf_violation(request: Request) -> bool:
    if request.method.upper() not in _UNSAFE:
        return False
    # Bearer-token API clients are not exposed to ambient-credential CSRF.
    if not request.cookies.get("session_token"):
        return False
    origin = request.headers.get("origin")
    if not origin or origin == "null":
        ref = request.headers.get("referer")
        origin = _origin_of(ref) if ref else None
        if origin is None:
            # Browsers always send Origin on cross-site unsafe requests;
            # absence means same-origin legacy UA or a non-browser client.
            return request.headers.get("origin") == "null"
    origin = origin.rstrip("/").lower()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").lower()
    if host and _origin_of(origin) and urlsplit(origin).netloc == host:
        return False
    return origin not in _allowed_origins()


# --------------------------------------------------------------------------
# Middleware
# --------------------------------------------------------------------------
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
}


async def security_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id")
    if not rid or not re.fullmatch(r"[A-Za-z0-9._-]{8,64}", rid):
        rid = uuid.uuid4().hex
    request.state.request_id = rid
    start = time.perf_counter()
    path = request.url.path

    if path.startswith("/api") and csrf_violation(request):
        response = JSONResponse({"detail": "Cross-site request blocked"}, status_code=403)
    else:
        decision = rate_limit_decision(request) if path.startswith("/api") else None
        if decision:
            bucket, retry = decision
            response = JSONResponse(
                {"detail": "Too many requests. Please wait and try again."},
                status_code=429, headers={"Retry-After": str(retry)})
            access_log.warning(json.dumps({"event": "rate_limited", "bucket": bucket,
                                           "path": path, "request_id": rid}))
        else:
            response = await call_next(request)

    for k, v in SECURITY_HEADERS.items():
        if k == "X-Frame-Options" and "content-security-policy" in response.headers:
            continue
        response.headers.setdefault(k, v)
    if path.startswith("/api"):
        response.headers.setdefault("Cache-Control", "no-store")
    response.headers["X-Request-ID"] = rid
    dur_ms = round((time.perf_counter() - start) * 1000, 1)
    if path.startswith("/api") and path != "/api/":
        access_log.info(json.dumps({
            "event": "http", "request_id": rid, "method": request.method,
            "path": redact(path), "status": response.status_code, "ms": dur_ms,
            "src": _h(_client_ip(request))[:12],
        }))
        if (request.method == "GET" and response.status_code == 200 and EXPORT_RE.search(path)):
            await _audit_export(request, path, rid)
    return response


async def _audit_export(request: Request, path: str, rid: str):
    try:
        from core.deps import get_current_user  # local import: avoid cycles
        from core.audit import audit
        user = await get_current_user(request, request.cookies.get("session_token"),
                                      request.headers.get("authorization"))
        if user:
            await audit(user, "data.export", target=path, target_type="export",
                        meta={"request_id": rid})
    except Exception:  # noqa: BLE001
        pass
