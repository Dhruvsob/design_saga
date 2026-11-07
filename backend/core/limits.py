"""Shared row limits.

Money, ledger, payroll and access-control reads load every row (to_list(None)) so totals
and permissions are never silently wrong. Plain display lists use MAX_LIST_ROWS, set far
above a studio's realistic volume, so records no longer drop off lists at 500-2,000 rows.
"""
MAX_LIST_ROWS = 20000
