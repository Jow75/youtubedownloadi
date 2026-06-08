"""
Seller-side license tool for Universal Media Downloader.
========================================================
Run this on YOUR machine to create license keys for customers. It uses the
secret in secret.key (generate it once with --init). Keep secret.key PRIVATE.

Examples
--------
  python license_tool.py --init                      # one-time: create secret.key
  python license_tool.py --my-id                      # show THIS computer's machine ID
  python license_tool.py --generate --customer "Jane" --machine-id UMD-ABCD-1234-5678 --days 30
  python license_tool.py --generate --customer "Bob"  --machine-id UMD-... --plan yearly
  python license_tool.py --verify UMDL-....

A record of every key generated is appended to license_records.csv (git-ignored).
"""

import argparse
import csv
import secrets
import sys
from datetime import date
from pathlib import Path

import licensing as lic

HERE = Path(__file__).resolve().parent
SECRET_FILE = HERE / "secret.key"
RECORDS = HERE / "license_records.csv"


def cmd_init():
    if SECRET_FILE.is_file():
        print("secret.key already exists. Refusing to overwrite "
              "(that would invalidate every key you've issued).")
        return 1
    SECRET_FILE.write_text(secrets.token_bytes(32).hex(), encoding="utf-8")
    print(f"Created {SECRET_FILE}. Keep it PRIVATE and back it up.")
    return 0


def cmd_my_id():
    print(lic.get_machine_id())
    return 0


def cmd_generate(args):
    if lic.using_dev_secret():
        print("WARNING: no secret.key found — using the INSECURE dev secret. "
              "Run `python license_tool.py --init` first for real keys.")
    if not args.customer or not args.machine_id:
        print("Need --customer and --machine-id.")
        return 1
    code = lic.generate_license(args.customer, args.machine_id,
                                days=args.days, plan=args.plan)
    ok, payload = lic.verify_license(code)
    print("\nLICENSE KEY (send this to the customer):\n")
    print("  " + code + "\n")
    print(f"  customer : {payload['c']}")
    print(f"  machine  : {payload['mid']}")
    print(f"  plan     : {payload['p']}")
    print(f"  issued   : {payload['i']}")
    print(f"  expires  : {payload['e']}")

    new = not RECORDS.is_file()
    with RECORDS.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "customer", "machine_id", "plan",
                        "issued", "expires", "code"])
        w.writerow([date.today().isoformat(), payload["c"], payload["mid"],
                    payload["p"], payload["i"], payload["e"], code])
    print(f"\n  (recorded in {RECORDS.name})")
    return 0


def cmd_verify(code):
    ok, res = lic.verify_license(code)
    print("VALID ✔" if ok else "INVALID �’")
    print(res)
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description="UMD seller-side license tool")
    p.add_argument("--init", action="store_true", help="create secret.key (once)")
    p.add_argument("--my-id", action="store_true", help="print this machine's ID")
    p.add_argument("--generate", action="store_true", help="generate a license key")
    p.add_argument("--verify", metavar="CODE", help="verify a license key")
    p.add_argument("--customer", help="customer name")
    p.add_argument("--machine-id", help="customer's machine ID (UMD-XXXX-XXXX-XXXX)")
    p.add_argument("--days", type=int, default=None, help="validity in days")
    p.add_argument("--plan", default="monthly",
                   choices=list(lic.PLAN_DAYS.keys()), help="plan (sets default days)")
    args = p.parse_args()

    if args.init:
        return cmd_init()
    if args.my_id:
        return cmd_my_id()
    if args.verify:
        return cmd_verify(args.verify)
    if args.generate:
        return cmd_generate(args)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
