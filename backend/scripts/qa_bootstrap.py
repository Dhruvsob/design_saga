"""Create a platform owner in a LOCAL, DISPOSABLE QA database only.

Used by the browser E2E harness (OPS-06). It refuses to run unless MONGO_URL
points at localhost and DB_NAME starts with ``design_saga_qa`` so it can never
touch production or a shared database. Tenants and users are then created
through the real API by the E2E setup, exercising normal validation/RBAC.

Usage (password is read from the environment, never printed):
    MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=design_saga_qa_e2e \
    QA_SUPERADMIN_EMAIL=owner@qa.test QA_PASSWORD=... python scripts/qa_bootstrap.py
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _guard() -> tuple[str, str, str, str]:
    url = os.environ.get("MONGO_URL", "")
    db_name = os.environ.get("DB_NAME", "")
    env = (os.environ.get("ENV") or os.environ.get("APP_ENV") or "").lower()
    host = urlparse(url).hostname or ""
    if host not in LOCAL_HOSTS:
        sys.exit("Refusing: MONGO_URL must point at localhost for QA bootstrap")
    if not db_name.startswith("design_saga_qa"):
        sys.exit("Refusing: DB_NAME must start with 'design_saga_qa'")
    if env in {"prod", "production"}:
        sys.exit("Refusing: production environment flag is set")
    email = os.environ.get("QA_SUPERADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("QA_PASSWORD", "")
    if not email.endswith((".test", "@qa.example.com")) or len(password) < 12:
        sys.exit("Refusing: QA_SUPERADMIN_EMAIL must use a .test or @qa.example.com address and QA_PASSWORD >= 12 chars")
    return url, db_name, email, password


async def main() -> None:
    url, db_name, email, password = _guard()
    import bcrypt
    from motor.motor_asyncio import AsyncIOMotorClient

    db = AsyncIOMotorClient(url)[db_name]
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode("ascii")
    now = datetime.now(timezone.utc).isoformat()
    await db.users.update_one(
        {"email": email},
        {"$set": {"password_hash": hashed, "role": "SuperAdmin", "is_active": True,
                  "approval_status": "approved", "name": "QA Platform Owner"},
         "$setOnInsert": {"user_id": "user_" + uuid.uuid4().hex[:12], "email": email,
                          "created_at": now}},
        upsert=True,
    )
    # Start every QA run from a known state: drop the owner's App PIN and
    # sessions (local disposable database only; guarded above).
    owner = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1})
    await db.user_app_locks.delete_many({"user_id": owner["user_id"]})
    await db.user_sessions.delete_many({"user_id": owner["user_id"]})
    print(f"QA platform owner ready in {db_name}")


if __name__ == "__main__":
    asyncio.run(main())
