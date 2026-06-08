"""
Shared license ledger for Universal Media Downloader (seller side).
Both license_admin.py (the GUI) and license_tool.py (the CLI) read and append
HERE, so there is ONE customer list. The file opens directly in Excel and
updates itself every time you issue a key.
"""

import csv
from pathlib import Path

RECORDS = Path(__file__).resolve().parent / "license_records.csv"
FIELDNAMES = ["timestamp", "customer", "phone", "email", "machine_id",
              "plan", "issued", "expires", "amount", "payment", "notes", "code"]


def load_records():
    """Return every issued license as a list of dicts (oldest first)."""
    if not RECORDS.is_file():
        return []
    with RECORDS.open(newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


def append_record(row):
    """Append one license row, migrating any older/narrower file to the full
    column set so the schema stays consistent."""
    rows = load_records()
    rows.append(row)
    with RECORDS.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (r.get(k, "") or "") for k in FIELDNAMES})
