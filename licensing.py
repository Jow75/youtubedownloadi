"""
Offline license system for Universal Media Downloader.
=====================================================
Machine-bound, HMAC-SHA256-signed, expiring license keys — works fully offline.
Adapted from a proven licensing design.

License code format:   UMDL-<base64url(payload)>.<base64url(signature[:16])>
Machine ID format:      UMD-XXXX-XXXX-XXXX   (from Windows MachineGuid + hostname)

SECURITY / SECRET HANDLING
--------------------------
The signing secret is loaded, in priority order, from:
  1. the UMD_LICENSE_SECRET environment variable, or
  2. a `secret.key` file next to this module (GIT-IGNORED — never committed), or
  3. a clearly-marked DEV placeholder (insecure; for local testing only).

This keeps the real secret OUT of the public repo. For a distributed build the
real secret.key is bundled with the app. (Note: like the reference system, this
is symmetric HMAC — the secret in a shared build is extractable. Fine for small
scale; upgrade to Ed25519 asymmetric signing later to harden.)
"""

import base64
import hashlib
import hmac
import json
import os
import platform
from datetime import date, datetime, timedelta
from pathlib import Path

APP_NAME = "UniversalMediaDownloader"
LICENSE_PREFIX = "UMDL-"
MACHINE_PREFIX = "UMD"
PLAN_DAYS = {"trial": 7, "monthly": 30, "yearly": 365, "lifetime": 36500}

# DEV-only placeholder. The REAL secret lives in secret.key / env (never in git).
_DEV_SECRET = "DEV-INSECURE-PLACEHOLDER-DO-NOT-SHIP"


def _module_dir():
    return Path(__file__).resolve().parent


def load_secret_str():
    env = os.environ.get("UMD_LICENSE_SECRET")
    if env and env.strip():
        return env.strip()
    keyfile = _module_dir() / "secret.key"
    if keyfile.is_file():
        return keyfile.read_text(encoding="utf-8").strip()
    return _DEV_SECRET


def _secret_bytes():
    s = load_secret_str()
    try:
        return bytes.fromhex(s)
    except ValueError:
        return s.encode("utf-8")


def using_dev_secret():
    return load_secret_str() == _DEV_SECRET


# --------------------------------------------------------------------------- #
# Machine ID
# --------------------------------------------------------------------------- #
def _raw_fingerprint():
    parts = []
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"SOFTWARE\Microsoft\Cryptography")
        guid, _ = winreg.QueryValueEx(k, "MachineGuid")
        winreg.CloseKey(k)
        parts.append(guid)
    except Exception:  # noqa: BLE001 (non-Windows / no permission)
        pass
    node = platform.node()
    if node:
        parts.append(node)
    if not parts:
        parts.append(os.environ.get("COMPUTERNAME", "unknown"))
        parts.append(os.environ.get("USERNAME", "unknown"))
    return "|".join(parts)


def get_machine_id():
    h = hashlib.sha256(_raw_fingerprint().encode("utf-8")).hexdigest()[:12].upper()
    return f"{MACHINE_PREFIX}-{h[:4]}-{h[4:8]}-{h[8:12]}"


# --------------------------------------------------------------------------- #
# Sign / verify
# --------------------------------------------------------------------------- #
def _b64e(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s):
    pad = (4 - len(s) % 4) % 4
    return base64.urlsafe_b64decode(s + "=" * pad)


def sign_payload(payload, secret=None):
    secret = secret if secret is not None else _secret_bytes()
    pj = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    pb = _b64e(pj.encode("utf-8"))
    sig = hmac.new(secret, pb.encode("utf-8"), hashlib.sha256).digest()[:16]
    return f"{LICENSE_PREFIX}{pb}.{_b64e(sig)}"


def verify_license(code, secret=None):
    secret = secret if secret is not None else _secret_bytes()
    code = (code or "").strip()
    if not code.startswith(LICENSE_PREFIX):
        return False, "Not a valid license code."
    parts = code[len(LICENSE_PREFIX):].split(".")
    if len(parts) != 2:
        return False, "Malformed license code."
    pb, sb = parts
    expected = _b64e(hmac.new(secret, pb.encode("utf-8"), hashlib.sha256).digest()[:16])
    if not hmac.compare_digest(sb, expected):
        return False, "Signature mismatch — key is fake or corrupted."
    try:
        payload = json.loads(_b64d(pb).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return False, "Could not decode license payload."
    if "e" not in payload or "mid" not in payload:
        return False, "License payload missing required fields."
    return True, payload


def generate_license(customer, machine_id, days=None, plan="monthly", secret=None):
    if days is None:
        days = PLAN_DAYS.get(plan, 30)
    today = date.today()
    payload = {
        "c": customer,
        "mid": machine_id or "",
        "p": plan,
        "i": today.isoformat(),
        "e": (today + timedelta(days=days)).isoformat(),
    }
    return sign_payload(payload, secret)


# --------------------------------------------------------------------------- #
# Client-side manager
# --------------------------------------------------------------------------- #
def config_dir():
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


class LicenseManager:
    def __init__(self):
        self.file = config_dir() / "license.dat"
        self.code = None
        self.payload = None
        self._load()

    def get_machine_id(self):
        return get_machine_id()

    def _load(self):
        if self.file.is_file():
            code = self.file.read_text(encoding="utf-8").strip()
            ok, res = verify_license(code)
            if ok:
                self.code, self.payload = code, res

    def activate(self, code):
        ok, res = verify_license(code)
        if not ok:
            return False, res
        if res.get("mid") and res["mid"] != self.get_machine_id():
            return False, "This key was issued for a different computer."
        exp = datetime.strptime(res["e"], "%Y-%m-%d").date()
        if date.today() > exp:
            return False, f"This key expired on {res['e']}."
        self.file.write_text(code.strip(), encoding="utf-8")
        self.code, self.payload = code.strip(), res
        days = (exp - date.today()).days
        return True, f"Activated! Valid until {res['e']} ({days} days left)."

    def is_licensed(self):
        if not self.code:
            return False
        ok, res = verify_license(self.code)
        if not ok:
            return False
        if res.get("mid") and res["mid"] != self.get_machine_id():
            return False
        exp = datetime.strptime(res["e"], "%Y-%m-%d").date()
        return date.today() <= exp

    def status(self):
        if not self.code:
            return "🔒 Unlicensed."
        ok, res = verify_license(self.code)
        if not ok:
            return "⚠️ Stored license is invalid."
        exp = datetime.strptime(res["e"], "%Y-%m-%d").date()
        days = (exp - date.today()).days
        if days < 0:
            return f"⛔ Expired on {res['e']}."
        who = res.get("c", "—")
        return f"✅ Licensed to {who} · expires {res['e']} ({days} days left)."

    def deactivate(self):
        try:
            self.file.unlink()
        except OSError:
            pass
        self.code = self.payload = None
