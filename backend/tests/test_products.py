"""P2.2 Product & Material Library: catalogue rules, append-only prices, files,
quotation snapshots, permissions and tenant isolation."""
import asyncio
import copy
import io
import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

import core.refs as refs
import routes.products as products
import services.local_files as lf


# ---------------------------------------------------------------- fake tenant-scoped db
def _values(doc, path):
    cur = [doc]
    for part in path.split("."):
        nxt = []
        for c in cur:
            if isinstance(c, list):
                for x in c:
                    if isinstance(x, dict) and part in x:
                        nxt.append(x[part])
            elif isinstance(c, dict) and part in c:
                nxt.append(c[part])
        cur = nxt
    out = []
    for c in cur:
        out.extend(c if isinstance(c, list) else [c])
    return out


def _match(doc, q):
    for k, v in (q or {}).items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in v):
                return False
            continue
        vals = _values(doc, k)
        if isinstance(v, dict) and any(x.startswith("$") for x in v):
            if "$ne" in v and v["$ne"] in vals:
                return False
            if "$regex" in v and not any(isinstance(x, str) and re.search(v["$regex"], x, re.I) for x in vals):
                return False
        elif v not in vals and not (v is None and not vals):
            return False
    return True


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction=1):
        self.rows.sort(key=lambda r: r.get(key) or "", reverse=direction == -1)
        return self

    async def to_list(self, _n=None):
        return [copy.deepcopy(r) for r in self.rows]


class _Coll:
    def __init__(self, org, rows=None):
        self.org, self.rows = org, rows if rows is not None else []

    def _q(self, q):
        return {**(q or {}), "org_id": self.org}

    def find(self, q=None, _p=None):
        return _Cursor([r for r in self.rows if _match(r, self._q(q))])

    async def find_one(self, q=None, _p=None):
        return next((copy.deepcopy(r) for r in self.rows if _match(r, self._q(q))), None)

    async def insert_one(self, doc):
        self.rows.append(copy.deepcopy({**doc, "org_id": self.org}))

    async def count_documents(self, q=None):
        return sum(1 for r in self.rows if _match(r, self._q(q)))

    async def update_one(self, q, u):
        for r in self.rows:
            if _match(r, self._q(q)):
                r.update(copy.deepcopy(u.get("$set", {})))
                for k, v in (u.get("$push") or {}).items():
                    r.setdefault(k, []).append(copy.deepcopy(v))
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    async def delete_one(self, q):
        before = len(self.rows)
        self.rows[:] = [r for r in self.rows if not _match(r, self._q(q))][:]
        return SimpleNamespace(deleted_count=before - len(self.rows))

    async def delete_many(self, q):
        return await self.delete_one(q)


class _DB:
    def __init__(self, org, shared):
        self.org, self.shared = org, shared

    def __getattr__(self, name):
        return _Coll(self.org, self.shared.setdefault(name, []))

    def __getitem__(self, name):
        return getattr(self, name)


DESIGNER = {"user_id": "u_des", "org_id": "org_a", "name": "Riya",
            "permissions": ["quotations.read", "quotations.create", "quotations.update", "vendors.read"]}
EMPLOYEE = {"user_id": "u_emp", "org_id": "org_a", "name": "Amit", "permissions": ["vendors.read"]}
HR = {"user_id": "u_hr", "org_id": "org_a", "name": "Hema", "permissions": ["employees.read"]}
DIRECTOR = {"user_id": "u_dir", "org_id": "org_a", "name": "Dev", "permissions": ["quotations.*", "vendors.*"]}


@pytest.fixture
def env(monkeypatch, tmp_path):
    shared = {"vendors_acc": [{"id": "ven_a", "org_id": "org_a", "name": "Atomberg Dealer"},
                              {"id": "ven_b", "org_id": "org_b", "name": "Other Co"}],
              "quotations_adv": []}
    who = {"user": DESIGNER}
    audits = []

    async def user(*_a, **_k):
        return who["user"]

    async def record(actor, action, **kw):
        audits.append(action)

    async def no_quota(_org):
        return None

    scoped = _DB("org_a", shared)
    monkeypatch.setattr(products, "sdb", scoped)
    monkeypatch.setattr(refs, "sdb", scoped)
    monkeypatch.setattr(products, "require_user", user)
    monkeypatch.setattr(products, "audit", record)
    monkeypatch.setattr(products, "tenant_storage_quota_bytes", no_quota)
    monkeypatch.setattr(products, "user_org_id", lambda u: u["org_id"])
    monkeypatch.setattr(lf, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(products, "business_today", lambda: __import__("datetime").date(2026, 11, 16))
    return SimpleNamespace(shared=shared, who=who, audits=audits, tmp=tmp_path)


def run(coro):
    return asyncio.run(coro)


FAN = {"name": "BLDC ceiling fan", "brand": "Atomberg", "model": "Renesa+ 1200", "category": "Fans",
       "finish": "Matt black", "unit": "nos", "specs": [{"label": "Sweep", "value": "1200 mm"},
                                                        {"label": "Power", "value": "28 W"},
                                                        {"label": "Remote", "value": "IR remote"}],
       "tags": ["BLDC", "bldc", "Remote"], "default_vendor_id": "ven_a", "preferred": True}


def create(**kw):
    return run(products.create_product(products.ProductIn(**{**FAN, **kw}), request=None))


def test_create_cleans_input_links_vendor_and_hides_storage(env):
    p = create()
    assert p["status"] == "active" and p["default_vendor_name"] == "Atomberg Dealer"
    assert p["tags"] == ["BLDC", "Remote"]                       # case-insensitive de-dup
    assert p["images"] == [] and p["latest_price"] is None and p["cover_url"] is None
    assert env.audits == ["product.create"]
    with pytest.raises(HTTPException) as foreign:
        create(default_vendor_id="ven_b")                         # another workspace's vendor
    assert foreign.value.status_code == 400
    with pytest.raises(Exception):
        products.ProductIn(name="x", product_url="javascript:alert(1)")


def test_search_filters_order_and_pagination(env):
    create()
    create(name="Pendant light", brand="Philips", model="Hue Pendant", category="Lighting", preferred=False,
           tags=["Dining"])
    old = create(name="Old fan", brand="Usha", model="Striker", category="Fans", preferred=False, tags=[])
    run(products.update_product(old["id"], products.ProductUpdate(status="discontinued"), request=None))

    out = run(products.list_products(request=None))
    assert [p["name"] for p in out["items"]] == ["BLDC ceiling fan", "Pendant light"]      # preferred first, discontinued hidden
    assert out["facets"]["categories"] == ["Fans", "Lighting"] and "Usha" not in out["facets"]["brands"]
    assert [p["name"] for p in run(products.list_products(request=None, q="renesa"))["items"]] == ["BLDC ceiling fan"]
    assert run(products.list_products(request=None, tag="Dining"))["total"] == 1
    assert run(products.list_products(request=None, status="discontinued"))["items"][0]["name"] == "Old fan"
    page2 = run(products.list_products(request=None, page=2, page_size=1))
    assert page2["total"] == 2 and [p["name"] for p in page2["items"]] == ["Pendant light"]
    assert "product.discontinue" in env.audits


def test_prices_are_append_only_and_latest_feeds_the_product(env):
    p = create()
    run(products.add_price(p["id"], products.PriceIn(price=4200, gst_pct=18, valid_from="2026-10-01"), request=None))
    run(products.add_price(p["id"], products.PriceIn(price=4450.456, source="quote", note="Diwali quote"), request=None))
    detail = run(products.get_product(p["id"], request=None))
    assert [x["price"] for x in detail["prices"]] == [4450.46, 4200]
    assert detail["latest_price"]["price"] == 4450.46 and detail["latest_price"]["vendor_name"] == "Atomberg Dealer"
    assert detail["prices"][0]["valid_from"] == "2026-11-16"
    paths = {(r.path, m) for r in products.router.routes for m in r.methods}
    assert not {("/products/{product_id}/prices/{price_id}", m) for m in ("PATCH", "PUT", "DELETE")} & paths
    with pytest.raises(HTTPException):
        run(products.add_price(p["id"], products.PriceIn(price=1, vendor_id="ven_b"), request=None))


def test_boq_line_is_a_snapshot_with_the_latest_price(env):
    p = create(sku="AT-RN-1200")
    run(products.add_price(p["id"], products.PriceIn(price=4450), request=None))
    line = run(products.product_boq_line(p["id"], request=None, room="Living Room"))
    assert line["code"] == "AT-RN-1200" and line["rate"] == 4450 and line["room"] == "Living Room"
    assert line["description"].startswith("BLDC ceiling fan - Atomberg Renesa+ 1200 (Matt black). Sweep: 1200 mm")
    assert line["vendor"] == "Atomberg Dealer" and line["product_id"] == p["id"]
    assert line["product_snapshot"]["price"] == 4450 and line["product_snapshot"]["spec_summary"].count(";") == 2
    run(products.update_product(p["id"], products.ProductUpdate(status="discontinued"), request=None))
    with pytest.raises(HTTPException) as gone:
        run(products.product_boq_line(p["id"], request=None))
    assert gone.value.status_code == 409


def test_used_products_cannot_be_deleted_unused_ones_can(env):
    env.who["user"] = DIRECTOR
    used, spare = create(), create(name="Spare")
    env.shared["quotations_adv"].append({"id": "q1", "org_id": "org_a",
                                         "boq": [{"category": "Fans", "items": [{"product_id": used["id"]}]}]})
    with pytest.raises(HTTPException) as exc:
        run(products.delete_product(used["id"], request=None))
    assert exc.value.status_code == 409 and "discontinued" in exc.value.detail
    run(products.add_price(spare["id"], products.PriceIn(price=10), request=None))
    assert run(products.delete_product(spare["id"], request=None)) == {"ok": True}
    assert not [r for r in env.shared["product_prices"] if r["product_id"] == spare["id"]]
    env.who["user"] = DESIGNER                                     # designers cannot delete
    with pytest.raises(HTTPException) as no:
        run(products.delete_product(used["id"], request=None))
    assert no.value.status_code == 403


def _png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, "PNG")
    return buf.getvalue()


def _upload(name, data):
    return UploadFile(filename=name, file=io.BytesIO(data))


def test_images_and_datasheets_are_typed_tenant_stored_and_served(env):
    p = create()
    with pytest.raises(HTTPException) as wrong:
        run(products.upload_product_file(p["id"], request=None, kind="image",
                                         upload=_upload("sheet.pdf", b"%PDF-1.4\n%%EOF")))
    assert wrong.value.status_code == 422
    assert not list(env.tmp.rglob("*.pdf"))                         # rejected upload removed
    out = run(products.upload_product_file(p["id"], request=None, kind="image", upload=_upload("fan.png", _png())))
    out = run(products.upload_product_file(p["id"], request=None, kind="datasheet",
                                           upload=_upload("spec.pdf", b"%PDF-1.4\n%%EOF")))
    assert out["cover_url"] == f"/api/products/{p['id']}/files/{out['images'][0]['id']}"
    assert "storage_key" not in str(out)
    stored = env.shared["products"][0]["images"][0]["storage_key"]
    assert stored.startswith("org_a/")
    resp = run(products.product_file(p["id"], out["images"][0]["id"], request=None))
    assert resp.media_type == "image/png" and resp.headers["x-content-type-options"] == "nosniff"
    out = run(products.remove_product_file(p["id"], out["datasheets"][0]["id"], request=None))
    assert out["datasheets"] == [] and len(list(env.tmp.rglob("*.pdf"))) == 0


def test_read_only_and_no_access_roles(env):
    p = create()
    env.who["user"] = EMPLOYEE
    assert run(products.list_products(request=None))["can_manage"] is False
    assert run(products.get_product(p["id"], request=None))["name"] == "BLDC ceiling fan"
    for call in (lambda: products.create_product(products.ProductIn(name="x"), request=None),
                 lambda: products.add_price(p["id"], products.PriceIn(price=1), request=None),
                 lambda: products.update_product(p["id"], products.ProductUpdate(name="y"), request=None)):
        with pytest.raises(HTTPException) as exc:
            run(call())
        assert exc.value.status_code == 403
    env.who["user"] = HR
    with pytest.raises(HTTPException):
        run(products.list_products(request=None))


def test_other_workspaces_products_are_invisible(env):
    p = create()
    other = _DB("org_b", env.shared)
    products.sdb = other                                          # monkeypatch restores it afterwards
    for call in (lambda: products.get_product(p["id"], request=None),
                 lambda: products.product_boq_line(p["id"], request=None),
                 lambda: products.add_price(p["id"], products.PriceIn(price=1), request=None)):
        with pytest.raises(HTTPException) as exc:
            run(call())
        assert exc.value.status_code == 404
    assert run(products.list_products(request=None))["total"] == 0
