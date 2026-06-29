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
    """STABLE, upgrade-proof home for the ledger: the per-user app-data folder
    (%APPDATA%\\UniversalMediaDownloader) — the SAME place the app keeps history,
    archive and license.dat. It survives rebuilds, installs AND uninstalls.

    It used to live next to the script/exe. That was the bug behind lost customer
    data: the frozen exe sat in dist\\, and the desktop build wipes dist\\ on every
    rebuild (Remove-Item dist) — silently destroying the seller's ledger. Persistent
    data must NEVER live in a build-output folder, so both modes now use config_dir().
    The 'Open in Excel'/'Open folder' buttons still work — they open this path."""
    import licensing
    return licensing.config_dir()


RECORDS = _data_dir() / "license_records.csv"


def _migrate_legacy_ledger():
    """One-time carry-over: if the stable ledger doesn't exist yet but an OLD
    next-to-script / next-to-exe ledger does, copy it into the stable location so
    previously-issued customers aren't lost on the move."""
    try:
        if RECORDS.exists():
            return
        candidates = [Path(__file__).resolve().parent / "license_records.csv"]
        if getattr(sys, "frozen", False):
            candidates.insert(0, Path(sys.executable).resolve().parent / "license_records.csv")
        for c in candidates:
            try:
                if c.is_file() and c.resolve() != RECORDS.resolve():
                    RECORDS.write_bytes(c.read_bytes())
                    return
            except OSError:
                pass
    except Exception:  # never let migration break startup
        pass


_migrate_legacy_ledger()
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
