"""
Sessione autenticata verso Yahoo Finance.

Gli endpoint dei fondamentali (quoteSummary) ora richiedono un cookie di
sessione + un "crumb". Questo modulo apre una sessione, ottiene i cookie e il
crumb, e li rende disponibili per le chiamate successive.
"""
from __future__ import annotations

from typing import Optional, Tuple

import requests

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def make_session() -> Tuple[requests.Session, Optional[str]]:
    """Ritorna (session, crumb). crumb puo' essere None se non ottenibile;
    in quel caso le chiamate quoteSummary vanno comunque tentate (degradano)."""
    s = requests.Session()
    s.headers.update(UA)
    crumb = None
    # 1) ottieni i cookie di sessione
    for url in ("https://fc.yahoo.com/", "https://finance.yahoo.com/"):
        try:
            s.get(url, timeout=12)
            if s.cookies:
                break
        except Exception:  # noqa: BLE001
            continue
    # 2) ottieni il crumb
    for host in ("query1", "query2"):
        try:
            r = s.get(f"https://{host}.finance.yahoo.com/v1/test/getcrumb",
                      timeout=12)
            txt = (r.text or "").strip()
            if r.status_code == 200 and txt and "<" not in txt and len(txt) < 40:
                crumb = txt
                break
        except Exception:  # noqa: BLE001
            continue
    return s, crumb
