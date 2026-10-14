"""CSV export hardening.

Spreadsheet apps execute cells starting with = + - @ (and tab/CR) as
formulas ("CSV injection"). Text cells are prefixed with an apostrophe so
they render literally; real numbers are left untouched.
"""
import csv

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")
MAX_EXPORT_ROWS = 50000


def safe_cell(value):
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = str(value)
    if text.startswith(_DANGEROUS):
        return "'" + text
    return text


class SafeWriter:
    def __init__(self, buf):
        self._w = csv.writer(buf)
        self.rows = 0

    def writerow(self, row):
        self.rows += 1
        if self.rows > MAX_EXPORT_ROWS + 1:
            from fastapi import HTTPException
            raise HTTPException(413, f"Export exceeds {MAX_EXPORT_ROWS} rows; narrow the date range")
        return self._w.writerow([safe_cell(v) for v in row])
