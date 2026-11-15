"""Concurrent-user load probe for a LOCAL or staging stack (refuses other hosts).

N virtual users loop over a typical first-screen mix for D seconds and the
probe reports throughput, latency percentiles and errors per endpoint.

  PROBE_BASE=http://127.0.0.1:8001 PROBE_LOGIN=... PROBE_PASSWORD=... PROBE_PIN=...
  python scripts/load_probe.py [users=25] [seconds=60] [think_seconds=0]
"""
import os
import statistics
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests

BASE = os.environ.get("PROBE_BASE", "http://127.0.0.1:8001")
if urlparse(BASE).hostname not in ("127.0.0.1", "localhost"):
    sys.exit("Refusing to load-test a non-local server.")
USERS = int(sys.argv[1]) if len(sys.argv) > 1 else 25
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 60
THINK = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0   # seconds between a user's clicks
MIX = ["/api/auth/me", "/api/dashboard/stats", "/api/notifications", "/api/projects",
       "/api/org/current", "/api/capacity", "/api/clients", "/api/leads"]


def session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login-password",
               json={"identifier": os.environ["PROBE_LOGIN"], "password": os.environ["PROBE_PASSWORD"]}, timeout=30)
    r.raise_for_status()
    s.headers["Authorization"] = "Bearer " + r.json()["session_token"]
    s.post(f"{BASE}/api/auth/pin/unlock", json={"pin": os.environ["PROBE_PIN"]}, timeout=30)
    assert s.get(f"{BASE}/api/projects", timeout=30).status_code == 200, "session not usable"
    return s


shared = session()   # one signed-in session; server-side cost is per request
lat = defaultdict(list)
errors = defaultdict(int)
codes = defaultdict(int)
lock = threading.Lock()
stop_at = time.time() + SECONDS


def user(n):
    s = requests.Session()
    s.headers.update(shared.headers)
    # Production nginx opens a new backend connection per request (no upstream
    # keep-alive pool); doing the same avoids racing uvicorn's 5 s keep-alive close.
    s.headers["Connection"] = "close"
    i = n
    while time.time() < stop_at:
        path = MIX[i % len(MIX)]
        i += 1
        t = time.perf_counter()
        try:
            r = s.get(BASE + path, timeout=60)
            ok = r.status_code == 200
            if not ok:
                with lock:
                    codes[r.status_code] += 1
        except requests.RequestException as exc:
            with lock:
                codes[type(exc).__name__ + ": " + str(exc)[:60]] += 1
            ok = False
        ms = (time.perf_counter() - t) * 1000
        with lock:
            lat[path].append(ms)
            if not ok:
                errors[path] += 1
        if THINK:
            time.sleep(THINK)


with ThreadPoolExecutor(max_workers=USERS) as pool:
    list(pool.map(user, range(USERS)))

total = sum(len(v) for v in lat.values())
allms = sorted(x for v in lat.values() for x in v)
pct = lambda xs, p: xs[min(len(xs) - 1, int(len(xs) * p))]  # noqa: E731
print(f"{USERS} users x {SECONDS}s: {total} requests, {total / SECONDS:.1f} req/s, "
      f"errors {sum(errors.values())}, p50 {pct(allms, .5):.0f} ms, p95 {pct(allms, .95):.0f} ms, max {allms[-1]:.0f} ms")
if codes:
    print("  error status codes:", dict(codes))
for path in MIX:
    xs = sorted(lat[path])
    if xs:
        print(f"  {path:24s} n={len(xs):5d}  p50 {statistics.median(xs):6.0f} ms  p95 {pct(xs, .95):6.0f} ms  errors {errors[path]}")
