"""
Desktop launcher for Universal Media Downloader.
================================================
Double-click target. Starts the Streamlit server (license-gated) on a free port
and opens it in the default browser — no terminal needed. Bundled ffmpeg / node
/ aria2c in ./bin are added to PATH so downloads work without separate installs.

Works both as a plain script (python desktop.py) and frozen with PyInstaller.
"""

import os
import socket
import sys
import threading
import time
import webbrowser


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


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def open_browser_when_ready(port):
    for _ in range(120):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                break
        except OSError:
            time.sleep(0.5)
    webbrowser.open(f"http://localhost:{port}")


def main():
    redirect_output_if_windowed()
    setup_environment()
    port = free_port()
    app_path = os.path.join(resource_dir(), "app.py")

    from streamlit import config as stcfg
    stcfg.set_option("server.headless", True)
    stcfg.set_option("server.port", port)
    stcfg.set_option("server.address", "127.0.0.1")
    stcfg.set_option("browser.gatherUsageStats", False)
    stcfg.set_option("global.developmentMode", False)

    threading.Thread(target=open_browser_when_ready, args=(port,), daemon=True).start()

    from streamlit.web import bootstrap
    bootstrap.run(app_path, False, [], {})


if __name__ == "__main__":
    main()
