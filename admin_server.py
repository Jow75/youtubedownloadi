"""
UMD Licensing — premium web admin (seller-only).
================================================
Serves a local, SaaS-style dashboard for issuing and tracking license keys.
It is a pure PRESENTATION layer: the licensing engine (licensing.py) and the
ledger (records.py) are reused unchanged — no functionality is altered.

    Double-click run_admin.bat        (or:  python admin_server.py)

Runs only on 127.0.0.1 (your machine). Never expose this or secret.key.
"""

import json
import os
import re
import socket
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from urllib.parse import urlparse, parse_qs

import licensing as lic
import records
import exports

HERE = os.path.dirname(os.path.abspath(__file__))
UI_FILE = os.path.join(HERE, "admin_ui.html")
MID_RE = re.compile(r"^UMD-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}$")
ALLOWED_UNITS = {"minutes", "hours", "days", "weeks", "months", "years"}
CLEAR_PIN = "4770"   # Danger Zone — the wipe-all confirmation PIN

DURATIONS = [
    {"label": "30 minutes", "kw": {"minutes": 30}},
    {"label": "1 hour", "kw": {"hours": 1}},
    {"label": "2 hours", "kw": {"hours": 2}},
    {"label": "3 hours", "kw": {"hours": 3}},
    {"label": "6 hours", "kw": {"hours": 6}},
    {"label": "12 hours", "kw": {"hours": 12}},
    {"label": "1 day", "kw": {"days": 1}},
    {"label": "2 days", "kw": {"days": 2}},
    {"label": "3 days", "kw": {"days": 3}},
    {"label": "1 week", "kw": {"weeks": 1}},
    {"label": "2 weeks", "kw": {"weeks": 2}},
    {"label": "1 month", "kw": {"months": 1}},
    {"label": "3 months", "kw": {"months": 3}},
    {"label": "6 months", "kw": {"months": 6}},
    {"label": "1 year", "kw": {"years": 1}},
    {"label": "2 years", "kw": {"years": 2}},
    {"label": "Lifetime", "kw": {"years": 100}},
]


def _to_float(x):
    try:
        return float(str(x).strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _month(iso):
    try:
        return lic.parse_dt(iso).strftime("%Y-%m")
    except Exception:  # noqa: BLE001
        return ""


def _last_months(now, n):
    out, y, m = [], now.year, now.month
    for i in range(n - 1, -1, -1):
        mm, yy = m - i, y
        while mm <= 0:
            mm += 12
            yy -= 1
        out.append(f"{yy:04d}-{mm:02d}")
    return out


def _status(expires, now):
    try:
        exp = lic.parse_dt(expires)
    except Exception:  # noqa: BLE001
        return "unknown", 0, "?"
    secs = (exp - now).total_seconds()
    if secs < 0:
        return "expired", int(secs // 86400), "expired"
    return (("expiring" if secs <= 7 * 86400 else "active"),
            int(secs // 86400), lic.human_left(exp, now))


def build_payload():
    now = datetime.now()
    enriched = []
    for r in records.load_records():
        st, days, human = _status(r.get("expires", ""), now)
        enriched.append({
            "customer": r.get("customer", ""), "machine_id": r.get("machine_id", ""),
            "phone": r.get("phone", ""), "email": r.get("email", ""),
            "plan": r.get("plan", ""), "issued": r.get("issued", ""),
            "expires": r.get("expires", ""), "amount": _to_float(r.get("amount", "")),
            "payment": r.get("payment", ""), "reference": r.get("reference", ""),
            "notes": r.get("notes", ""),
            "code": r.get("code", ""), "status": st, "days_left": days,
            "human_left": human,
        })

    groups = {}
    for r in enriched:
        groups.setdefault(r["machine_id"], []).append(r)
    customers = []
    for mid, recs in groups.items():
        recs.sort(key=lambda x: x["issued"])
        latest = recs[-1]
        total_paid = sum(x["amount"] for x in recs)
        customers.append({
            "machine_id": mid, "customer": latest["customer"],
            "phone": latest["phone"], "email": latest["email"],
            "plan": latest["plan"], "issued": latest["issued"],
            "expires": latest["expires"], "status": latest["status"],
            "days_left": latest["days_left"], "human_left": latest["human_left"],
            "payment": latest["payment"], "total_paid": total_paid,
            "license_count": len(recs), "is_renewal": len(recs) > 1,
            "high_value": total_paid >= 1000,
            "first_seen": recs[0]["issued"],
            "history": list(reversed(recs)),
        })
    customers.sort(key=lambda c: c["issued"], reverse=True)

    active = sum(c["status"] == "active" for c in customers)
    expiring = sum(c["status"] == "expiring" for c in customers)
    expired = sum(c["status"] == "expired" for c in customers)
    total_rev = sum(r["amount"] for r in enriched)
    this_month = now.strftime("%Y-%m")
    month_rev = sum(r["amount"] for r in enriched if _month(r["issued"]) == this_month)

    kpis = {
        "total_licenses": len(enriched), "active": active,
        "expiring_soon": expiring, "expired": expired,
        "monthly_revenue": round(month_rev, 2), "total_revenue": round(total_rev, 2),
        "total_customers": len(customers),
        "renewals": sum(c["is_renewal"] for c in customers),
    }

    months = _last_months(now, 6)
    rev_by = {m: 0.0 for m in months}
    lic_by = {m: 0 for m in months}
    for r in enriched:
        mk = _month(r["issued"])
        if mk in rev_by:
            rev_by[mk] += r["amount"]
            lic_by[mk] += 1
    lic_cum, running = [], sum(1 for r in enriched if _month(r["issued"]) and _month(r["issued"]) < months[0])
    for m in months:
        running += lic_by[m]
        lic_cum.append({"label": m, "value": running})
    first_seen = {}
    for c in customers:
        fm = _month(min(h["issued"] for h in c["history"]))
        first_seen[fm] = first_seen.get(fm, 0) + 1
    cust_cum, crun = [], sum(v for k, v in first_seen.items() if k and k < months[0])
    for m in months:
        crun += first_seen.get(m, 0)
        cust_cum.append({"label": m, "value": crun})
    buckets = [["<= 7 days", 0], ["8-30 days", 0], ["31-90 days", 0], ["90+ days", 0]]
    for c in customers:
        if c["status"] == "expired":
            continue
        d = c["days_left"]
        idx = 0 if d <= 7 else 1 if d <= 30 else 2 if d <= 90 else 3
        buckets[idx][1] += 1

    charts = {
        "revenue_by_month": [{"label": m, "value": round(rev_by[m], 2)} for m in months],
        "licenses_cumulative": lic_cum,
        "customers_cumulative": cust_cum,
        "expiration_forecast": [{"label": b[0], "value": b[1]} for b in buckets],
    }
    return {
        "machine_id": lic.get_machine_id(),
        "using_dev_secret": lic.using_dev_secret(),
        "durations": DURATIONS, "kpis": kpis, "charts": charts,
        "customers": customers,
    }


def do_generate(data):
    name = (data.get("customer") or "").strip()
    mid = (data.get("machine_id") or "").strip().upper()
    if len(name) < 2:
        return 400, {"ok": False, "error": "Enter a customer name (2+ letters)."}
    if not MID_RE.match(mid):
        return 400, {"ok": False, "error": f"'{mid}' is not a valid Machine ID (UMD-XXXX-XXXX-XXXX)."}
    kw = data.get("duration") or {}
    kw = {k: int(v) for k, v in kw.items() if k in ALLOWED_UNITS} if isinstance(kw, dict) else {}
    if not kw or any(v < 1 for v in kw.values()):
        return 400, {"ok": False, "error": "Pick a valid duration."}
    plan = (data.get("plan_label") or "custom").strip()
    expiry = lic.expiry_from_duration(**kw)
    code = lic.generate_license(name, mid, expiry=expiry, plan=plan)
    ok, payload = lic.verify_license(code)
    if not ok:
        return 500, {"ok": False, "error": f"Self-check failed: {payload}"}
    records.append_record({
        "timestamp": datetime.now().replace(microsecond=0).isoformat(),
        "customer": name, "phone": (data.get("phone") or "").strip(),
        "email": (data.get("email") or "").strip(), "machine_id": mid, "plan": plan,
        "issued": payload["i"], "expires": payload["e"],
        "amount": str(data.get("amount") or "").strip(),
        "payment": (data.get("payment") or "").strip(),
        "reference": (data.get("reference") or "").strip(),
        "notes": (data.get("notes") or "").strip(), "code": code,
    })
    return 200, {"ok": True, "code": code, "payload": payload, "machine_id": mid,
                 "plan": plan, "human_left": lic.human_left(lic.parse_dt(payload["e"]))}


def _fmt_dt(iso):
    try:
        return lic.parse_dt(iso).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return iso or ""


def _export_rows():
    """Full per-license rows (newest first) for an export."""
    now = datetime.now()
    headers = ["Customer", "Phone", "Email", "Machine ID", "Plan", "Status",
               "Issued", "Expires", "Amount", "Payment", "Reference", "Notes", "License Key"]
    rows = []
    for r in sorted(records.load_records(), key=lambda x: x.get("issued", ""), reverse=True):
        st, _d, _h = _status(r.get("expires", ""), now)
        rows.append([
            r.get("customer", ""), r.get("phone", ""), r.get("email", ""),
            r.get("machine_id", ""), r.get("plan", ""), st.capitalize(),
            _fmt_dt(r.get("issued", "")), _fmt_dt(r.get("expires", "")),
            _to_float(r.get("amount", "")), r.get("payment", ""),
            r.get("reference", ""), r.get("notes", ""), r.get("code", ""),
        ])
    return headers, rows


def do_export(fmt):
    """Write the ledger to csv/xlsx/pdf next to the data file, then open it."""
    headers, rows = _export_rows()
    out_dir = records.RECORDS.parent
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sub = f"{len(rows)} license(s) · exported {datetime.now():%Y-%m-%d %H:%M}"
    try:
        if fmt == "csv":
            path = exports.write_csv(out_dir / f"UMD_licenses_{stamp}.csv", headers, rows)
        elif fmt == "xlsx":
            path = exports.write_xlsx(out_dir / f"UMD_licenses_{stamp}.xlsx", headers, rows)
        elif fmt == "pdf":
            # A compact, readable column set for the landscape PDF report.
            idx = [0, 1, 3, 4, 5, 7, 8, 9, 10]
            pdf_h = [headers[i] for i in idx]
            pdf_rows = [[r[i] for i in idx] for r in rows]
            path = exports.write_pdf(out_dir / f"UMD_licenses_{stamp}.pdf", pdf_h, pdf_rows,
                                     title="UMD — License Records", subtitle=sub)
        else:
            return 400, {"ok": False, "error": "Unknown export format."}
    except Exception as e:  # noqa: BLE001
        return 500, {"ok": False, "error": f"Export failed: {e}"}
    try:
        os.startfile(str(path))  # noqa: S606  (Windows: open in Excel / PDF viewer)
    except Exception:  # noqa: BLE001
        pass
    return 200, {"ok": True, "path": str(path), "count": len(rows)}


def do_clear(data):
    """Danger Zone: wipe ALL records, gated by the PIN. Always backs up first."""
    pin = str((data or {}).get("pin") or "").strip()
    if pin != CLEAR_PIN:
        return 403, {"ok": False, "error": "Incorrect PIN — nothing was deleted."}
    removed, backup = records.clear_records()
    return 200, {"ok": True, "removed": removed, "backup": backup}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                with open(UI_FILE, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, b"admin_ui.html is missing", "text/plain")
            return
        if path == "/api/bootstrap":
            self._send(200, build_payload())
            return
        if path == "/api/export":
            q = parse_qs(urlparse(self.path).query)
            fmt = (q.get("fmt", ["csv"])[0] or "csv").lower()
            status, body = do_export(fmt)
            self._send(status, body)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route in ("/api/generate", "/api/clear"):
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send(400, {"ok": False, "error": "Bad JSON"})
                return
            status, body = do_generate(data) if route == "/api/generate" else do_clear(data)
            self._send(status, body)
            return
        self._send(404, {"error": "not found"})

    def log_message(self, *_a):  # keep the console quiet
        pass


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def make_server():
    """Create the bound server + its port (already listening). The caller runs
    serve_forever() — in a window app that's a background thread."""
    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server, port


def main():
    """Standalone/browser mode (no native window) — used as a fallback."""
    server, port = make_server()
    url = f"http://localhost:{port}/"
    threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(url)),
                     daemon=True).start()
    print(f"UMD Licensing admin is running at {url}")
    print("Leave this window open while you work. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
