"""
Desktop launcher for Universal Media Downloader.
================================================
Double-click target. It runs the Streamlit server locally and shows the app in
a REAL native window (PyWebView / Windows WebView2) — no browser tab, so there's
nothing to "disconnect". Closing the window quits the app. Bundled ffmpeg / node
/ aria2c in ./bin are added to PATH so downloads work without separate installs.

If a native window can't be created (e.g. WebView2 runtime missing), it falls
back to opening the default browser, so the app always works.

Works both as a plain script (python desktop.py) and frozen with PyInstaller.
"""

import os
import socket
import sys
import threading
import time
import webbrowser

WINDOW_TITLE = "Universal Media Downloader"


def app_dir():
    """Folder containing the exe (frozen) or this script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_dir():
    """Folder containing bundled app.py/downloader.py/licensing.py."""
    return getattr(sys, "_MEIPASS", app_dir())


def redirect_output_if_windowed():
    """A windowed (no-console) frozen build has sys.stdout/err == None.
    Streamlit writes log lines there, which would crash the app, so send that
    output to a log file in %LOCALAPPDATA% instead (handy for debugging too)."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or app_dir()
    log_dir = os.path.join(base, "UniversalMediaDownloader")
    try:
        os.makedirs(log_dir, exist_ok=True)
        log = open(os.path.join(log_dir, "umd-log.txt"), "a",
                   encoding="utf-8", buffering=1)
    except OSError:
        log = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


def setup_environment():
    # Bundled binaries (ffmpeg, ffprobe, aria2c, node) live next to the exe.
    bin_dir = os.path.join(app_dir(), "bin")
    if os.path.isdir(bin_dir):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    # Shipped builds are license-gated; UTF-8 keeps emoji titles safe.
    os.environ.setdefault("UMD_ENFORCE_LICENSE", "1")
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def _patch_signal_for_thread():
    """Streamlit installs SIGINT/SIGTERM handlers, but signal.signal() only
    works on the main thread — and we run the server off-thread so the main
    thread is free for the GUI window. Swallow that one ValueError; we shut
    down by closing the window, not by signals."""
    import signal
    _orig = signal.signal

    def _safe(sig, handler):
        try:
            return _orig(sig, handler)
        except ValueError:
            return None

    signal.signal = _safe


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_for_port(port, timeout=120):
    for _ in range(timeout * 2):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def run_server(port, app_path):
    from streamlit import config as stcfg
    stcfg.set_option("server.headless", True)
    stcfg.set_option("server.port", port)
    stcfg.set_option("server.address", "127.0.0.1")
    stcfg.set_option("browser.gatherUsageStats", False)
    stcfg.set_option("global.developmentMode", False)
    from streamlit.web import bootstrap
    bootstrap.run(app_path, False, [], {})


def _serve_forever_in_browser(url):
    """Fallback when no native window can be created: open the browser and keep
    the server process alive."""
    webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def main():
    redirect_output_if_windowed()
    setup_environment()
    _patch_signal_for_thread()

    port = free_port()
    app_path = os.path.join(resource_dir(), "app.py")
    threading.Thread(target=run_server, args=(port, app_path), daemon=True).start()

    url = f"http://localhost:{port}"
    if not wait_for_port(port):
        print("Server did not start in time; opening in browser instead.")
        _serve_forever_in_browser(url)
        return

    try:
        import webview
        webview.create_window(WINDOW_TITLE, url, width=1200, height=820,
                              min_size=(940, 600))
        webview.start()           # blocks until the window is closed
    except Exception as exc:       # noqa: BLE001 — any GUI/backend failure
        print(f"Native window unavailable ({exc!r}); opening in browser.")
        _serve_forever_in_browser(url)
        return

    # Window closed -> quit hard so the background server thread stops cleanly.
    os._exit(0)


if __name__ == "__main__":
    main()
