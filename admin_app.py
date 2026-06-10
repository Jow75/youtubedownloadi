"""
One-click launcher for the License Console (seller-only).
=========================================================
Turns admin_server.py into a clean double-click application that opens the
premium License Console in its OWN native window (Windows WebView2) — no console
and no browser tab. Falls back to the browser if no WebView2 is available.
Build it with build_admin_exe.ps1.

SECURITY: the frozen exe embeds secret.key (the signing key) because it has to
sign licenses. Keep LicenseConsole.exe PRIVATE — never share or upload it.
"""

import os
import sys
import threading
import time

WINDOW_TITLE = "License Console — Universal Media Downloader"


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

    server, port = admin_server.make_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"

    try:
        import webview
        webview.create_window(WINDOW_TITLE, url, width=1320, height=880,
                              min_size=(1000, 640))
        webview.start()           # blocks until the window is closed
    except Exception as exc:       # noqa: BLE001 — no WebView2 etc.
        print(f"Native window unavailable ({exc!r}); opening in browser.")
        import webbrowser
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        return
    os._exit(0)


if __name__ == "__main__":
    main()
