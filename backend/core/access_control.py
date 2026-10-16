"""Shared same-tenant project and task visibility rules."""
from fastapi import HTTPException

from core.rbac import has_permission
from core.scoped_db import sdb


def require_permission(user: dict, permission: str) -> None:
    if not has_permission(user, permission):
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")


async def user_identity_ids(user: dict) -> set[str]:
    ids = {user["user_id"]}
    terms = [{"user_id": user["user_id"]}]
    if user.get("email"):
        terms.append({"email": user["email"]})
    async for employee in sdb.employees.find({"$or": terms}, {"_id": 0, "id": 1}):
        if employee.get("id"):
            ids.add(employee["id"])
    return ids


def merge_query(base: dict | None, visibility: dict | None) -> dict:
    if not base:
        return visibility or {}
    if not visibility:
        return base
    return {"$and": [base, visibility]}


async def project_visibility_query(user: dict) -> dict:
    if (has_permission(user, "projects.delete")
            or has_permission(user, "finance.read")
            or has_permission(user, "invoices.read")):
        return {}
    ids = list(await user_identity_ids(user))
    return {"$or": [
        {"team_ids": {"$in": ids}},
        {"project_manager_id": {"$in": ids}},
        {"created_by": user["user_id"]},
    ]}


async def visible_project_ids(user: dict) -> list[str]:
    rows = await sdb.projects.find(
        await project_visibility_query(user), {"_id": 0, "id": 1}
    ).to_list(2000)
    return [row["id"] for row in rows if row.get("id")]


async def get_visible_project(user: dict, project_id: str, permission: str = "projects.read",
                              projection: dict | None = None) -> dict:
    require_permission(user, permission)
    query = merge_query({"id": project_id}, await project_visibility_query(user))
    project = await sdb.projects.find_one(query, projection or {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def task_visibility_query(user: dict) -> dict:
    if has_permission(user, "tasks.delete"):
        return {}
    ids = list(await user_identity_ids(user))
    project_ids = await visible_project_ids(user)
    terms = [
        {"project_id": {"$in": project_ids}},
        {"assignee_id": {"$in": ids}},
        {"assignees": {"$in": ids}},
        {"created_by": user["user_id"]},
    ]
    if user.get("name"):
        terms.append({"assignee_name": user["name"]})
    return {"$or": terms}


async def personal_task_visibility_query(user: dict) -> dict:
    """Tasks suitable for a user's personal calendar, without role-wide access."""
    ids = list(await user_identity_ids(user))
    terms = [
        {"assignee_id": {"$in": ids}},
        {"assignees": {"$in": ids}},
        {"created_by": user["user_id"]},
    ]
    if user.get("name"):
        terms.append({"assignee_name": user["name"]})
    return {"$or": terms}


async def get_visible_task(user: dict, task_id: str, permission: str = "tasks.read",
                           projection: dict | None = None) -> dict:
    require_permission(user, permission)
    query = merge_query({"id": task_id}, await task_visibility_query(user))
    task = await sdb.tasks.find_one(query, projection or {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
