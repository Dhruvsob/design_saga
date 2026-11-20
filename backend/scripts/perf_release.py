"""Release timings (FINAL_TEST_RESULTS.md, performance).

Fresh local workspace; builds the documents this release touched (a 45-line
quotation BOQ, a 40-line invoice, a 30-line purchase order, 30 selections)
and times the requests a person waits for. Reports median and p95 over
SAMPLES warm requests (the first request of each kind is discarded).
Local only (refuses other hosts through accounting_acceptance).
"""
from __future__ import annotations

import os
import statistics
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(__file__))
from accounting_acceptance import PIN, new_workspace, ok  # noqa: E402

SAMPLES = int(os.environ.get("SAMPLES", "20"))


def timed(c, method: str, path: str, n: int = SAMPLES, **kw) -> list[float]:
    c.request(method, path, **kw)  # warm-up, discarded
    out = []
    for _ in range(n):
        t = time.perf_counter()
        r = c.request(method, path, **kw)
        out.append((time.perf_counter() - t) * 1000)
        if r.status_code >= 400:
            raise RuntimeError(f"{path} -> {r.status_code} {r.text[:200]}")
    return out


def p95(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[max(0, int(round(0.95 * len(xs))) - 1)]


def main() -> None:
    c = new_workspace()
    client = ok(c.post("/api/clients", json={"name": "Perf Client"}))
    project = ok(c.post("/api/projects", json={"name": "Perf Villa", "client_id": client["id"],
                                               "project_type": "Residential", "engagement_type": "turnkey"}))
    long = "Supply and install BWP plywood carcass with laminate, liner, soft-close hardware and edge banding " * 2
    q = ok(c.post("/api/quotations-adv", json={"type": "turnkey", "project_title": "Perf", "client_id": client["id"]}))
    ok(c.put(f"/api/quotations-adv/{q['id']}", json={"boq": [{"category": f"Cat {k}", "items": [
        {"description": long, "unit": "sqft", "quantity": 10 + n, "rate": 1500 + n, "margin_pct": 12}
        for n in range(15)]} for k in range(3)]}))
    inv = ok(c.post("/api/invoices", json={"client_id": client["id"], "doc_type": "invoice", "status": "draft", "tax_rate": 18,
                                           "items": [{"description": long, "quantity": 1, "rate": 1000 + n} for n in range(40)]}))
    vendor = ok(c.post("/api/vendors", json={"name": f"Perf Vendor {uuid.uuid4().hex[:4]}"}))
    vid = vendor.get("id") or vendor.get("vendor", {}).get("id")
    po = ok(c.post("/api/purchase-orders", json={"vendor_id": vid, "lines": [
        {"item_name": f"Item {n}", "description": long, "quantity": 2, "unit_price": 4500 + n, "tax_rate": 18} for n in range(30)]}))
    po = po.get("purchase_order", po)
    for n in range(30):
        ok(c.post(f"/api/projects/{project['id']}/selections", json={"room": f"Room {n % 6}", "item": f"Finish {n}",
                                                                     "specification": long[:300]}))

    def unlock_and_dashboard():
        ok(c.post("/api/auth/pin/lock"))
        t = time.perf_counter()
        ok(c.post("/api/auth/pin/unlock", json={"pin": PIN}))
        ok(c.get("/api/dashboard/stats"))
        ok(c.get("/api/dashboard/my-day"))
        return (time.perf_counter() - t) * 1000

    rows = {
        "project search (q=Villa)": timed(c, "GET", "/api/projects", params={"q": "Villa"}),
        "profit and loss (FY)": timed(c, "GET", "/api/accounting/reports/pl", params={"fy": "2026-27"}),
        "project selections, 30 rows": timed(c, "GET", f"/api/projects/{project['id']}/selections"),
    }
    # Exports are limited to 30 a minute per person: 9 samples per document
    # kind, with a pause between kinds.
    for name, path in (("quotation PDF, 45-line BOQ", f"/api/quotations-adv/{q['id']}/pdf"),
                       ("invoice PDF, 40 lines", f"/api/invoices/{inv['id']}/pdf"),
                       ("purchase order PDF, 30 lines", f"/api/purchase-orders/{po['id']}/pdf")):
        time.sleep(61)
        rows[name] = timed(c, "GET", path, n=9)
    time.sleep(61)   # PIN unlock is limited to 10 a minute
    unlock_and_dashboard()  # warm-up
    unlock = []
    for _ in range(8):
        unlock.append(unlock_and_dashboard())
        time.sleep(0.5)
    rows["PIN unlock + dashboard data"] = unlock
    print(f"{'request':<34} {'n':>3} {'median ms':>10} {'p95 ms':>8}")
    for name, xs in rows.items():
        print(f"{name:<34} {len(xs):>3} {statistics.median(xs):>10.0f} {p95(xs):>8.0f}")


if __name__ == "__main__":
    main()
