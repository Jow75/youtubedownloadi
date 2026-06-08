"""
Universal Media Downloader — License Admin (PRIVATE, seller-only)
================================================================
A click-and-go desktop tool for ISSUING license keys. Run it on YOUR computer
(the one that holds secret.key). NEVER give this file or secret.key to anyone.

    Double-click  run_admin.bat        (or:  python license_admin.py)

What it does:
  * Paste a customer's Machine ID (UMD-XXXX-XXXX-XXXX), or use this PC's ID.
  * Pick ANY length — 30 min / 1 h / days / weeks / months / years / custom.
  * Click "Generate Key" -> the key is created, copied to clipboard, and logged.
  * See every key you've issued in a live table (green = active, red = expired).
  * The log is license_records.csv — opens in Excel, updates itself.
"""

import os
import re
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import licensing as lic
import records

MID_RE = re.compile(r"^UMD-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}$")

# (label, kwargs for lic.expiry_from_duration).  "Custom..." -> None
DURATIONS = [
    ("30 minutes", {"minutes": 30}),
    ("1 hour", {"hours": 1}),
    ("2 hours", {"hours": 2}),
    ("3 hours", {"hours": 3}),
    ("6 hours", {"hours": 6}),
    ("12 hours", {"hours": 12}),
    ("1 day", {"days": 1}),
    ("2 days", {"days": 2}),
    ("3 days", {"days": 3}),
    ("1 week", {"weeks": 1}),
    ("2 weeks", {"weeks": 2}),
    ("1 month", {"months": 1}),
    ("3 months", {"months": 3}),
    ("6 months", {"months": 6}),
    ("1 year", {"years": 1}),
    ("2 years", {"years": 2}),
    ("Lifetime", {"years": 100}),
    ("Custom...", None),
]
DURATION_LABELS = [d[0] for d in DURATIONS]
DURATION_MAP = dict(DURATIONS)
CUSTOM_UNITS = ["minutes", "hours", "days", "weeks", "months", "years"]


def _short(iso):
    """Trim an ISO datetime to 'YYYY-MM-DD HH:MM' for the table."""
    if not iso:
        return ""
    try:
        return lic.parse_dt(iso).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return iso


class AdminApp:
    def __init__(self, root):
        self.root = root
        root.title("Universal Media Downloader - License Admin (PRIVATE)")
        root.geometry("1040x720")
        root.minsize(900, 600)

        self._build_header()
        self._build_form()
        self._build_output()
        self._build_dashboard()
        self._build_table()
        self._build_toolbar()

        self.use_this_pc()
        self.refresh_table()
        self._warn_if_dev_secret()

    # ------------------------------------------------------------------ UI
    def _build_header(self):
        bar = ttk.Frame(self.root, padding=(12, 8))
        bar.pack(fill=tk.X)
        ttk.Label(bar, text="License Admin",
                  font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT)
        ttk.Label(bar, text="   PRIVATE TOOL - DO NOT DISTRIBUTE",
                  foreground="#c0392b",
                  font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)

    def _build_form(self):
        f = ttk.LabelFrame(self.root, text="Generate a key", padding=10)
        f.pack(fill=tk.X, padx=12, pady=(0, 8))
        for i in range(4):
            f.columnconfigure(i, weight=1)

        self.v_name = tk.StringVar()
        self.v_mid = tk.StringVar()
        self.v_amount = tk.StringVar(value="0")
        self.v_payment = tk.StringVar(value="Cash")
        self.v_notes = tk.StringVar()
        self.v_duration = tk.StringVar(value="1 hour")
        self.v_qty = tk.StringVar(value="1")
        self.v_unit = tk.StringVar(value="hours")

        ttk.Label(f, text="Customer name *").grid(row=0, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.v_name).grid(
            row=0, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(f, text="Machine ID *").grid(row=0, column=2, sticky="w")
        midbox = ttk.Frame(f)
        midbox.grid(row=0, column=3, sticky="ew", padx=4)
        midbox.columnconfigure(0, weight=1)
        ttk.Entry(midbox, textvariable=self.v_mid).grid(row=0, column=0, sticky="ew")
        ttk.Button(midbox, text="This PC", width=8,
                   command=self.use_this_pc).grid(row=0, column=1, padx=(4, 0))

        ttk.Label(f, text="Duration *").grid(row=1, column=0, sticky="w")
        self.cb_dur = ttk.Combobox(f, textvariable=self.v_duration,
                                   values=DURATION_LABELS, state="readonly")
        self.cb_dur.grid(row=1, column=1, sticky="ew", padx=4, pady=3)
        self.cb_dur.bind("<<ComboboxSelected>>", lambda e: self._toggle_custom())

        self.custom = ttk.Frame(f)
        self.custom.grid(row=1, column=2, columnspan=2, sticky="ew", padx=4)
        ttk.Label(self.custom, text="length:").pack(side=tk.LEFT)
        ttk.Spinbox(self.custom, from_=1, to=9999, width=6,
                    textvariable=self.v_qty).pack(side=tk.LEFT, padx=4)
        ttk.Combobox(self.custom, textvariable=self.v_unit, values=CUSTOM_UNITS,
                     state="readonly", width=10).pack(side=tk.LEFT)
        self._toggle_custom()

        ttk.Label(f, text="Amount paid").grid(row=2, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.v_amount).grid(
            row=2, column=1, sticky="ew", padx=4, pady=3)
        ttk.Label(f, text="Payment").grid(row=2, column=2, sticky="w")
        ttk.Combobox(f, textvariable=self.v_payment, state="readonly",
                     values=["Cash", "M-Pesa", "Bank", "PayPal", "Free", "Other"]
                     ).grid(row=2, column=3, sticky="ew", padx=4)

        ttk.Label(f, text="Notes").grid(row=3, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.v_notes).grid(
            row=3, column=1, columnspan=3, sticky="ew", padx=4, pady=3)

        btns = ttk.Frame(f)
        btns.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(btns, text="Generate Key", command=self.generate).pack(side=tk.LEFT)
        ttk.Button(btns, text="Clear", command=self.clear_form).pack(side=tk.LEFT, padx=6)

    def _toggle_custom(self):
        if self.v_duration.get() == "Custom...":
            self.custom.grid()
        else:
            self.custom.grid_remove()

    def _build_output(self):
        f = ttk.LabelFrame(self.root, text="Generated key (already on your clipboard)",
                           padding=10)
        f.pack(fill=tk.X, padx=12, pady=(0, 8))
        self.v_code = tk.StringVar()
        ttk.Entry(f, textvariable=self.v_code, font=("Consolas", 9),
                  state="readonly").pack(fill=tk.X)
        row = ttk.Frame(f)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(row, text="Copy key", command=self.copy_code).pack(side=tk.LEFT)
        ttk.Button(row, text="Copy Machine ID",
                   command=self.copy_mid).pack(side=tk.LEFT, padx=6)
        self.v_detail = tk.StringVar(value="No key generated yet.")
        ttk.Label(f, textvariable=self.v_detail,
                  foreground="#555").pack(anchor="w", pady=(6, 0))

    def _build_dashboard(self):
        f = ttk.Frame(self.root, padding=(12, 0))
        f.pack(fill=tk.X)
        self.v_dash = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.v_dash,
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")

    def _build_table(self):
        f = ttk.LabelFrame(self.root, text="Issued licenses (click a row to re-issue)",
                           padding=8)
        f.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 8))
        cols = ("customer", "machine_id", "plan", "issued", "expires", "status", "amount")
        heads = ("Customer", "Machine ID", "Plan", "Issued", "Expires", "Status", "Paid")
        widths = (150, 150, 95, 130, 130, 140, 55)
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=10)
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="w")
        self.tree.tag_configure("active", foreground="#1e7e34")
        self.tree.tag_configure("expired", foreground="#c0392b")
        self.tree.bind("<<TreeviewSelect>>", self._on_row)
        sb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_toolbar(self):
        f = ttk.Frame(self.root, padding=(12, 0, 12, 10))
        f.pack(fill=tk.X)
        ttk.Button(f, text="Open list in Excel",
                   command=self.open_excel).pack(side=tk.LEFT)
        ttk.Button(f, text="Open folder",
                   command=self.open_folder).pack(side=tk.LEFT, padx=6)
        ttk.Button(f, text="Refresh", command=self.refresh_table).pack(side=tk.LEFT)
        ttk.Label(f, text=f"My Machine ID: {lic.get_machine_id()}",
                  foreground="#555").pack(side=tk.RIGHT)

    # -------------------------------------------------------------- actions
    def use_this_pc(self):
        self.v_mid.set(lic.get_machine_id())

    def _expiry(self):
        label = self.v_duration.get()
        if label == "Custom...":
            try:
                qty = int(self.v_qty.get())
            except ValueError:
                raise ValueError("Custom length must be a whole number.")
            if qty < 1:
                raise ValueError("Custom length must be at least 1.")
            kwargs = {self.v_unit.get(): qty}
            label = f"{qty} {self.v_unit.get()}"
        else:
            kwargs = DURATION_MAP[label]
        return label, lic.expiry_from_duration(**kwargs)

    def generate(self):
        name = self.v_name.get().strip()
        mid = self.v_mid.get().strip().upper()
        if len(name) < 2:
            messagebox.showwarning("Missing", "Enter a customer name (2+ letters).")
            return
        if not MID_RE.match(mid):
            messagebox.showwarning(
                "Bad Machine ID",
                f"'{mid}' is not a valid Machine ID.\nExpected: UMD-XXXX-XXXX-XXXX")
            return
        try:
            plan, expiry = self._expiry()
        except ValueError as exc:
            messagebox.showwarning("Duration", str(exc))
            return

        code = lic.generate_license(name, mid, expiry=expiry, plan=plan)
        ok, payload = lic.verify_license(code)
        if not ok:
            messagebox.showerror("Error", f"Key failed self-check: {payload}")
            return

        records.append_record({
            "timestamp": datetime.now().replace(microsecond=0).isoformat(),
            "customer": name, "phone": "", "email": "", "machine_id": mid,
            "plan": plan, "issued": payload["i"], "expires": payload["e"],
            "amount": self.v_amount.get().strip(),
            "payment": self.v_payment.get(), "notes": self.v_notes.get().strip(),
            "code": code,
        })

        self.v_code.set(code)
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self.v_detail.set(
            f"OK  {name}  -  {plan}  -  expires {payload['e']} "
            f"({lic.human_left(lic.parse_dt(payload['e']))} left).  Key copied to clipboard.")
        self.refresh_table()

    def copy_code(self):
        if self.v_code.get():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.v_code.get())

    def copy_mid(self):
        if self.v_mid.get():
            self.root.clipboard_clear()
            self.root.clipboard_append(self.v_mid.get())

    def clear_form(self):
        self.v_name.set("")
        self.v_amount.set("0")
        self.v_notes.set("")
        self.use_this_pc()

    def refresh_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        rows = records.load_records()
        now = datetime.now()
        active = expired = 0
        for r in reversed(rows):  # newest first
            exp_s = r.get("expires", "")
            try:
                exp = lic.parse_dt(exp_s)
                live = now <= exp
                status = (f"ACTIVE - {lic.human_left(exp, now)} left"
                          if live else "EXPIRED")
                tag = "active" if live else "expired"
            except Exception:  # noqa: BLE001
                status, tag, live = "?", "", False
            active += 1 if live else 0
            expired += 0 if live else 1
            self.tree.insert("", "end", tags=(tag,), values=(
                r.get("customer", ""), r.get("machine_id", ""), r.get("plan", ""),
                _short(r.get("issued", "")), _short(exp_s), status,
                r.get("amount", "")))
        self.v_dash.set(
            f"Total keys: {len(rows)}     Active: {active}     Expired: {expired}")

    def _on_row(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        self.v_name.set(vals[0])
        self.v_mid.set(vals[1])

    def open_excel(self):
        if not records.RECORDS.is_file():
            messagebox.showinfo("No file yet", "Generate a key first.")
            return
        try:
            os.startfile(str(records.RECORDS))  # noqa: S606 — Windows only
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not open", str(exc))

    def open_folder(self):
        try:
            os.startfile(str(records.RECORDS.parent))  # noqa: S606
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Could not open", str(exc))

    def _warn_if_dev_secret(self):
        if lic.using_dev_secret():
            messagebox.showwarning(
                "No secret.key",
                "No secret.key found - using the INSECURE dev placeholder.\n"
                "Keys made now will NOT match your shipped app.\n\n"
                "Run once in this folder:  python license_tool.py --init")


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")  # crisper on Windows; ignored if absent
    except tk.TclError:
        pass
    AdminApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
