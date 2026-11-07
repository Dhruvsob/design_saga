"""Money, ledger, payroll and access reads must never stop at a row cap (R1, DS-100).

A capped read there silently gives wrong totals or hides projects once a company
grows past the cap, so those modules may only use to_list(None).
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
FULL_READ_MODULES = [
    "routes/accounting.py", "routes/vendors.py", "routes/finance_extras.py",
    "routes/employee_advances.py", "routes/payroll.py", "core/access_control.py",
]
CAPPED = re.compile(r"\.to_list\(\s*\d+\s*\)")


def test_money_and_access_reads_are_uncapped():
    offenders = []
    for rel in FULL_READ_MODULES:
        for no, line in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            if CAPPED.search(line) and ".limit(" not in line:   # explicit .limit(n) is intended
                offenders.append(f"{rel}:{no}: {line.strip()}")
    assert offenders == []


def test_display_lists_use_the_shared_limit():
    from core.limits import MAX_LIST_ROWS
    assert MAX_LIST_ROWS >= 20000
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    assert not re.search(r"\.to_list\((500|1000|2000)\)", server)
