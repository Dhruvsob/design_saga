"""
READ-ONLY database inspection for migration planning.

Connection strings are read ONLY from environment variables:
  - SRC_MONGO_URL : source database (previous ERP) - provided via secret/env
  - TGT_MONGO_URL : target database (current ERP) - defaults to backend .env MONGO_URL

This script performs ZERO writes. It only lists dbs/collections, counts docs,
and samples field keys so we can build a migration plan.
"""
import os
import sys
import json
from collections import Counter
from pymongo import MongoClient


def mask(uri: str) -> str:
    if not uri:
        return "(none)"
    try:
        if "@" in uri:
            proto, rest = uri.split("://", 1)
            creds, host = rest.split("@", 1)
            return f"{proto}://****:****@{host.split('/')[0]}"
        return uri.split("/")[0]
    except Exception:
        return "(masked)"


def pick_databases(client):
    """Return candidate business databases, skipping admin/local/config."""
    skip = {"admin", "local", "config"}
    dbs = []
    for name in client.list_database_names():
        if name in skip:
            continue
        dbs.append(name)
    return dbs


def sample_keys(coll, limit=25):
    key_counter = Counter()
    sample_doc = None
    for i, doc in enumerate(coll.find({}, limit=limit)):
        if sample_doc is None:
            sample_doc = {k: type(v).__name__ for k, v in doc.items()}
        for k in doc.keys():
            key_counter[k] += 1
    return key_counter, sample_doc


def inspect(label, uri, force_db=None):
    print("=" * 70)
    print(f"[{label}] {mask(uri)}")
    print("=" * 70)
    if not uri:
        print("  !! No URI provided in environment. Skipping.\n")
        return
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=15000)
        client.admin.command("ping")
    except Exception as e:
        print(f"  !! Connection failed: {type(e).__name__}: {e}\n")
        return

    if force_db:
        db_names = [force_db]
    else:
        db_names = pick_databases(client)
    print(f"  Databases: {db_names}\n")

    for dbn in db_names:
        db = client[dbn]
        colls = db.list_collection_names()
        print(f"  --- DB: {dbn}  ({len(colls)} collections) ---")
        rows = []
        for c in sorted(colls):
            try:
                cnt = db[c].estimated_document_count()
            except Exception:
                cnt = db[c].count_documents({})
            rows.append((c, cnt))
        # print counts
        for c, cnt in rows:
            print(f"    {c:<32} {cnt:>8}")
        print()
        # deep sample only for non-empty collections
        for c, cnt in rows:
            if cnt == 0:
                continue
            keys, sample = sample_keys(db[c])
            print(f"    ~ {dbn}.{c}: top keys -> {list(keys.keys())[:20]}")
            if sample:
                print(f"      sample types -> {json.dumps(sample)[:400]}")
        print()
    client.close()


if __name__ == "__main__":
    src = os.environ.get("SRC_MONGO_URL", "")
    tgt = os.environ.get("TGT_MONGO_URL", os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    tgt_db = os.environ.get("TGT_DB_NAME", "test_database")

    inspect("SOURCE (provided URL)", src)
    inspect("TARGET (current ERP - local dev)", tgt, force_db=tgt_db)
