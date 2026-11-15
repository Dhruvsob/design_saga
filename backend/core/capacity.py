"""Capacity planning maths (P2.5): who is free and who is overbooked, by week.

Pure functions so the rules are easy to test and explain:

* Capacity of a person in a week = their working days that week (weekly
  offs, workspace holidays and approved leave removed) x their hours per day
  (weekly hours / working days in a normal week; 45 h a week if not set).
* Planned load = estimated hours of their open tasks, spread evenly over the
  working days between the task's start and due dates. A task with only a due
  date is planned in the week it is due. Work that is overdue, or planned for
  days already past, still has to be done, so it lands from today onward in
  the current week. Tasks shared by several people are split equally.
* Past weeks show hours actually logged on timesheets; the current week shows
  logged hours so far plus what is still planned.
"""
from datetime import date, timedelta
from typing import Iterable, Optional

DEFAULT_WEEKLY_HOURS = 45.0


def parse(value) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def is_working(d: date, offs: set[int], holidays: set[str]) -> bool:
    return d.weekday() not in offs and d.isoformat() not in holidays


def working_days(start: date, end: date, offs: set[int], holidays: set[str]) -> list[date]:
    out, d = [], start
    while d <= end:
        if is_working(d, offs, holidays):
            out.append(d)
        d += timedelta(days=1)
    return out


def hours_per_day(weekly_hours: Optional[float], offs: set[int]) -> float:
    days = max(1, 7 - len(offs))
    return round(float(weekly_hours or DEFAULT_WEEKLY_HOURS) / days, 4)


def spread(task: dict, today: date, offs: set[int], holidays: set[str]) -> dict[str, float]:
    """Remaining estimated hours of one task by week (ISO Monday -> hours)."""
    est = float(task.get("estimate_hours") or 0)
    due = parse(task.get("due_date"))
    if est <= 0 or not due:
        return {}
    start = parse(task.get("start_date")) or monday(due)
    start = min(start, due)
    if due < today:                     # overdue: still to do, from today to the end of this week
        start, end = today, monday(today) + timedelta(days=6)
    else:
        start, end = max(start, today), due
    days = working_days(start, end, offs, holidays) or [end]
    per_day = est / len(days)
    out: dict[str, float] = {}
    for d in days:
        key = monday(d).isoformat()
        out[key] = out.get(key, 0.0) + per_day
    return out


def week_capacity(week: date, day_hours: float, offs: set[int], holidays: set[str],
                  leave_days: set[str]) -> tuple[float, int, int]:
    """(capacity hours, holiday count, leave-day count) for the week starting `week`."""
    days = [week + timedelta(days=n) for n in range(7)]
    work = [d for d in days if d.weekday() not in offs]
    hol = [d for d in work if d.isoformat() in holidays]
    leave = [d for d in work if d.isoformat() not in holidays and d.isoformat() in leave_days]
    free = len(work) - len(hol) - len(leave)
    return round(max(0, free) * day_hours, 2), len(hol), len(leave)


def leave_dates(leaves: Iterable[dict], window_start: date, window_end: date) -> set[str]:
    out = set()
    for lv in leaves:
        a, b = parse(lv.get("from_date")), parse(lv.get("to_date"))
        if not a:
            continue
        b = b or a
        d = max(a, window_start)
        while d <= min(b, window_end):
            out.add(d.isoformat())
            d += timedelta(days=1)
    return out


def band(pct: Optional[float]) -> str:
    """Heatmap band for a load/capacity ratio."""
    if pct is None:
        return "off"
    if pct > 1.0:
        return "over"
    if pct >= 0.85:
        return "full"
    if pct >= 0.5:
        return "busy"
    return "light"
