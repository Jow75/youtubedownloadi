"""
Publisher / contact info for Universal Media Downloader.
========================================================
One place for the author's credit + contact channels, shown in the app (and
especially on the activation screen, so anyone who's handed a copy knows who to
contact for a license). Pure data — safe to import anywhere.
"""

APP_NAME = "Universal Media Downloader"
VERSION = "4.1"

PUBLISHER = "George (Jowgei)"
COUNTRY = "Kenya"
EMAIL = "phantomtyper.review@gmail.com"
WEBSITE = "https://baziqhue.co.ke/"
PHONES = ["+254799553292", "+12103296074"]  # both WhatsApp
COPYRIGHT = "Copyright (c) 2026 George (Jowgei)"


def _wa(phone):
    """A wa.me link needs digits only (no +, spaces)."""
    return "https://wa.me/" + "".join(ch for ch in phone if ch.isdigit())


def contact_md(heading=True):
    """A compact markdown block with clickable email / WhatsApp / website."""
    lines = []
    if heading:
        lines.append(f"**{APP_NAME}** — published by **{PUBLISHER}**, {COUNTRY}")
    lines.append(f"📧 Email: [{EMAIL}](mailto:{EMAIL})")
    wa = " · ".join(f"[{p}]({_wa(p)})" for p in PHONES)
    lines.append(f"💬 WhatsApp: {wa}")
    lines.append(f"🌐 Website: [{WEBSITE}]({WEBSITE})")
    return "  \n".join(lines)
