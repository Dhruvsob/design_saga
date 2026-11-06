"""Studio / Project calendar scope reaches Google Calendar (DS-097)."""
import asyncio

import core.google_calendar as gc


def _body(monkeypatch, source_type, doc, project=None):
    async def name(_org, pid):
        return project if pid else None

    async def no_attendees(*_a, **_k):
        return []
    monkeypatch.setattr(gc, "_project_name", name)
    monkeypatch.setattr(gc, "_attendee_emails", no_attendees)
    return asyncio.run(gc.event_body("org_a", source_type, doc))


def test_project_event_carries_project_in_title_link_and_scope(monkeypatch):
    b = _body(monkeypatch, "calendar_event",
              {"id": "evt_1", "title": "Site visit", "date": "2026-11-10", "project_id": "p1"}, "3BHK Satellite")
    assert b["summary"] == "[3BHK Satellite] Site visit"
    assert "Project: 3BHK Satellite" in b["description"] and "/projects/p1" in b["description"]
    assert b["extendedProperties"]["private"]["designSagaScope"] == "project"


def test_studio_event_is_labelled_studio(monkeypatch):
    b = _body(monkeypatch, "calendar_event", {"id": "evt_2", "title": "Team meeting", "date": "2026-11-10"})
    assert b["summary"] == "Studio: Team meeting"
    assert b["extendedProperties"]["private"]["designSagaScope"] == "studio"


def test_project_task_prefixes_project_and_keeps_stable_id(monkeypatch):
    doc = {"id": "t1", "title": "Working drawings", "due_date": "2026-11-12", "project_id": "p1", "status": "todo"}
    first = _body(monkeypatch, "task", doc, "Villa")
    again = _body(monkeypatch, "task", doc, "Villa")
    assert first["summary"] == "[Villa] Task: Working drawings"
    assert first["id"] == again["id"]          # same Google event id -> no duplicates on resync
