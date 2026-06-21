"""
Shared license ledger for Universal Media Downloader (seller side).
Both license_admin.py (the GUI) and license_tool.py (the CLI) read and append
HERE, so there is ONE customer list. The file opens directly in Excel and
updates itself every time you issue a key.
"""

import csv
import sys
from pathlib import Path


def _data_dir():
    """Where the ledger lives. As a normal script: next to this file (the repo,
    so the dev's existing CSV keeps working). Frozen into the License Console
    exe: next to the exe (portable, opens straight in Excel), falling back to
    %APPDATA% if the exe folder isn't writable."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        try:
            probe = exe_dir / ".umd_write_test"
            probe.write_text("x", encoding="utf-8")
            probe.unlink()
            return exe_dir
        except OSError:
            import licensing
            return licensing.config_dir()
    return Path(__file__).resolve().parent


RECORDS = _data_dir() / "license_records.csv"
# "reference" = the payment's transaction code (M-Pesa code / bank ref / PayPal id).
FIELDNAMES = ["timestamp", "customer", "phone", "email", "machine_id",
              "plan", "issued", "expires", "amount", "payment", "reference",
              "notes", "code"]


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


def clear_records():
    """DANGER ZONE: wipe ALL records. Backs the ledger up to a timestamped file
    first (so a mistake is recoverable), then truncates to just the header.
    Returns (rows_removed, backup_path_or_None)."""
    from datetime import datetime
    rows = load_records()
    backup = None
    if RECORDS.is_file() and rows:
        backup = RECORDS.with_name(f"license_records_backup_{datetime.now():%Y%m%d_%H%M%S}.csv")
        try:
            backup.write_bytes(RECORDS.read_bytes())
        except OSError:
            backup = None
    with RECORDS.open("w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore").writeheader()
    return len(rows), (str(backup) if backup else None)
