"""Task dependencies and baselines (P2.8). Pure functions; callers persist.

A dependency is finish-to-start: a task can start the day after everything it
depends on is due. When a task's finish moves later, its successors that would
now start too early move forward by the same rule, keeping their length, and the
change ripples down the chain. Successors are never pulled earlier
automatically, and finished or cancelled tasks never move.
"""
from __future__ import annotations

from collections import deque
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

FROZEN_LANES = ("done",)
FROZEN_DETAIL = ("Completed", "Cancelled")


def parse(value) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def span(task: dict) -> Tuple[Optional[date], Optional[date]]:
    """(start, finish). A task with only a due date is one day long."""
    due = parse(task.get("due_date"))
    start = parse(task.get("start_date")) or due
    if start and due and due < start:
        due = start
    return start, due


def creates_cycle(tasks: Dict[str, dict], task_id: str, new_deps: Iterable[str]) -> bool:
    """Would making `task_id` depend on `new_deps` create a loop?

    Edges run predecessor -> successor; with the new edges in place, a loop
    exists when walking successors from `task_id` leads back to it."""
    new_deps = list(new_deps)
    if task_id in new_deps:
        return True
    succ: Dict[str, List[str]] = {}
    for tid, t in tasks.items():
        deps = new_deps if tid == task_id else (t.get("depends_on") or [])
        for d in deps:
            succ.setdefault(d, []).append(tid)
    if task_id not in tasks:
        for d in new_deps:
            succ.setdefault(d, []).append(task_id)
    seen, queue = set(), deque([task_id])
    while queue:
        for nxt in succ.get(queue.popleft(), []):
            if nxt == task_id:
                return True
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def _frozen(task: dict) -> bool:
    return task.get("status") in FROZEN_LANES or task.get("status_detail") in FROZEN_DETAIL


def reschedule(tasks: Dict[str, dict], changed: Iterable[str]) -> Dict[str, dict]:
    """Return {task_id: {"start_date", "due_date"}} for successors that must move.

    `tasks` holds every task of the project with its *new* dates already applied.
    """
    succ: Dict[str, List[str]] = {}
    for tid, t in tasks.items():
        for d in t.get("depends_on") or []:
            if d in tasks:
                succ.setdefault(d, []).append(tid)
    moved: Dict[str, dict] = {}
    queue = deque(changed)
    guard = 0
    while queue and guard < 10000:
        guard += 1
        cur = queue.popleft()
        for nxt in succ.get(cur, []):
            t = {**tasks[nxt], **moved.get(nxt, {})}
            if _frozen(t):
                continue
            start, due = span(t)
            if not start:
                continue
            earliest = None
            for d in t.get("depends_on") or []:
                if d not in tasks:
                    continue
                _, pdue = span({**tasks[d], **moved.get(d, {})})
                if pdue and (earliest is None or pdue + timedelta(days=1) > earliest):
                    earliest = pdue + timedelta(days=1)
            if earliest and start < earliest:
                length = (due - start) if due else timedelta(0)
                new = {"start_date": earliest.isoformat(), "due_date": (earliest + length).isoformat()}
                moved[nxt] = new
                tasks[nxt] = {**tasks[nxt], **new}
                queue.append(nxt)
    return moved


def baseline_variance(task: dict) -> Optional[int]:
    """Days the current finish is later (+) or earlier (-) than the baseline finish."""
    base = parse((task.get("baseline") or {}).get("due_date"))
    _, due = span(task)
    if not base or not due:
        return None
    return (due - base).days
