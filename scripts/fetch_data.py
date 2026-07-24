"""
Scarica i dati di S&P 500, Dow Jones e Nasdaq da Yahoo Finance (endpoint
pubblici, senza chiave API), calcola indicatori e analisi e scrive
docs/data.json.

Eseguito da GitHub Actions (che ha internet pieno). In locale, in ambienti
con rete limitata, usare `seed_data.py` per generare dati dimostrativi.

Uso:
    python scripts/fetch_data.py            # scrive docs/data.json
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from typing import Dict, List, Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analysis  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "data.json")

from yahoo_auth import make_session  # noqa: E402

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
}

# sessione autenticata (cookie + crumb) per i fondamentali
SESSION, CRUMB = make_session()

# Indici e ETF proxy per i fondamentali (gli indici non hanno P/E diretto).
INDICES = [
    {"name": "S&P 500", "symbol": "^GSPC", "etf": "SPY", "stooq": "^spx"},
    {"name": "Dow Jones", "symbol": "^DJI", "etf": "DIA", "stooq": "^dji"},
    {"name": "Nasdaq", "symbol": "^IXIC", "etf": "QQQ", "stooq": "^ndq"},
]


def fetch_chart_yahoo(symbol: str, rng: str = "2y", interval: str = "1d") -> Optional[Dict]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": rng, "interval": interval, "includePrePost": "false"}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=20)
            if r.status_code == 200:
                data = r.json()
                res = data["chart"]["result"][0]
                ts = res["timestamp"]
                q = res["indicators"]["quote"][0]
                dates, o, h, l, c, v = [], [], [], [], [], []
                for i, t in enumerate(ts):
                    if None in (q["open"][i], q["high"][i], q["low"][i], q["close"][i]):
                        continue
                    dates.append(dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"))
                    o.append(float(q["open"][i]))
                    h.append(float(q["high"][i]))
                    l.append(float(q["low"][i]))
                    c.append(float(q["close"][i]))
                    v.append(float(q["volume"][i] or 0))
                if len(c) > 60:
                    return {"dates": dates, "open": o, "high": h, "low": l,
                            "close": c, "volume": v}
        except Exception as e:  # noqa: BLE001
            print(f"  Yahoo tentativo {attempt+1} fallito per {symbol}: {e}")
        time.sleep(1.5 * (attempt + 1))
    return None


def fetch_chart_stooq(stooq_symbol: str) -> Optional[Dict]:
    """Fallback: CSV giornaliero da Stooq."""
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    try:
        r = requests.get(url, headers=UA, timeout=20)
        if r.status_code != 200 or "Date" not in r.text[:50]:
            return None
        lines = r.text.strip().splitlines()[1:]
        dates, o, h, l, c, v = [], [], [], [], [], []
        for ln in lines[-520:]:
            parts = ln.split(",")
            if len(parts) < 6:
                continue
            try:
                dates.append(parts[0])
                o.append(float(parts[1])); h.append(float(parts[2]))
                l.append(float(parts[3])); c.append(float(parts[4]))
                v.append(float(parts[5]) if parts[5] not in ("", "N/D") else 0.0)
            except ValueError:
                continue
        if len(c) > 60:
            return {"dates": dates, "open": o, "high": h, "low": l,
                    "close": c, "volume": v}
    except Exception as e:  # noqa: BLE001
        print(f"  Stooq fallito per {stooq_symbol}: {e}")
    return None


def fetch_fundamentals(etf: str) -> Dict:
    """P/E, yield e altri dati dall'ETF proxy tramite Yahoo quoteSummary."""
    modules = "summaryDetail,defaultKeyStatistics,price"
    r = None
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v10/finance/quoteSummary/{etf}"
        params = {"modules": modules}
        if CRUMB:
            params["crumb"] = CRUMB
        try:
            resp = SESSION.get(url, params=params, timeout=20)
            if resp.status_code == 200:
                r = resp
                break
        except Exception:  # noqa: BLE001
            continue
    try:
        if r is None:
            return {"proxy_etf": etf}
        res = r.json()["quoteSummary"]["result"][0]
        sd = res.get("summaryDetail", {})
        ks = res.get("defaultKeyStatistics", {})

        def raw(d, k):
            v = d.get(k, {})
            return v.get("raw") if isinstance(v, dict) else None

        out = {
            "proxy_etf": etf,
            "pe": raw(sd, "trailingPE"),
            "yield": (raw(sd, "yield") or 0) * 100 if raw(sd, "yield") is not None else None,
            "beta": raw(ks, "beta") or raw(sd, "beta"),
            "day_high": raw(sd, "dayHigh"),
            "day_low": raw(sd, "dayLow"),
        }
        return {k: (round(v, 2) if isinstance(v, float) else v)
                for k, v in out.items() if v is not None}
    except Exception as e:  # noqa: BLE001
        print(f"  Fondamentali {etf} non disponibili: {e}")
        return {"proxy_etf": etf}


def build() -> Dict:
    indices_out: List[Dict] = []
    source = "Yahoo Finance"
    for spec in INDICES:
        print(f"Scarico {spec['name']} ({spec['symbol']})...")
        chart = fetch_chart_yahoo(spec["symbol"])
        if chart is None:
            print("  Yahoo non disponibile, provo Stooq...")
            chart = fetch_chart_stooq(spec["stooq"])
            if chart is not None:
                source = "Stooq (fallback)"
        if chart is None:
            raise RuntimeError(f"Impossibile scaricare dati per {spec['name']}")
        fund = fetch_fundamentals(spec["etf"])
        indices_out.append(
            analysis.build_index_analysis(
                spec["name"], spec["symbol"],
                chart["dates"], chart["open"], chart["high"],
                chart["low"], chart["close"], chart["volume"],
                fundamentals=fund,
            )
        )
        time.sleep(0.5)

    return {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": source,
        "demo": False,
        "market": analysis.market_summary(indices_out),
        "indices": indices_out,
    }


def main():
    data = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Scritto {OUT} — fase mercato: {data['market']['phase']} "
          f"(fonte: {data['source']})")


if __name__ == "__main__":
    main()
