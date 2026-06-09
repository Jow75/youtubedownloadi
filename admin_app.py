"""
One-click launcher for the License Console (seller-only).
=========================================================
This is the packaging entry point that turns admin_server.py into a clean
double-click application: NO console / CMD window, it just opens the premium
License Console in your browser. Build it with build_admin_exe.ps1.

SECURITY: the frozen exe embeds secret.key (the signing key) because it has to
sign licenses. Keep LicenseConsole.exe PRIVATE — never share or upload it.
"""

import os
import sys


def _redirect_if_windowed():
    """A windowed (no-console) build has sys.stdout/err == None; admin_server's
    print()s would crash. Send them to a log file instead."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    base = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
            or os.path.dirname(sys.executable))
    log_dir = os.path.join(base, "UniversalMediaDownloader")
    try:
        os.makedirs(log_dir, exist_ok=True)
        log = open(os.path.join(log_dir, "admin-log.txt"), "a",
                   encoding="utf-8", buffering=1)
    except OSError:
        log = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


def _wire_frozen_paths():
    """When frozen, point the licensing secret + UI file at the bundle."""
    if not getattr(sys, "frozen", False):
        return
    base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    keyfile = os.path.join(base, "secret.key")
    if os.path.isfile(keyfile) and not os.environ.get("UMD_LICENSE_SECRET"):
        try:
            with open(keyfile, encoding="utf-8") as f:
                os.environ["UMD_LICENSE_SECRET"] = f.read().strip()
        except OSError:
            pass


def main():
    _redirect_if_windowed()
    _wire_frozen_paths()
    import admin_server
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        admin_server.UI_FILE = os.path.join(base, "admin_ui.html")
    admin_server.main()


if __name__ == "__main__":
    main()
