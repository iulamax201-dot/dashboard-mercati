"""
Genera un docs/stocks.json DIMOSTRATIVO senza accesso a internet, così che la
pagina titoli.html mostri qualcosa prima del primo aggiornamento reale.

Dati sintetici, marcati come demo. Uso:
    python scripts/seed_stocks.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stock_analysis  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "stocks.json")

SEEDS = [
    {"name": "Nvidia", "ticker": "NVDA", "cur": "USD", "mkt": "NasdaqGS", "theme": "Tech · AI / Semiconduttori", "start": 118, "drift": 0.0011, "vol": 0.028},
    {"name": "Microsoft", "ticker": "MSFT", "cur": "USD", "mkt": "NasdaqGS", "theme": "Tech · AI / Cloud", "start": 430, "drift": 0.0006, "vol": 0.015},
    {"name": "Oracle", "ticker": "ORCL", "cur": "USD", "mkt": "NYSE", "theme": "Tech · AI / Cloud / Database", "start": 185, "drift": 0.0009, "vol": 0.019},
    {"name": "Apple", "ticker": "AAPL", "cur": "USD", "mkt": "NasdaqGS", "theme": "Tech · Consumer tech", "start": 215, "drift": 0.0004, "vol": 0.016},
    {"name": "ASML", "ticker": "ASML", "cur": "USD", "mkt": "NasdaqGS", "theme": "Tech · Semiconduttori", "start": 720, "drift": 0.0007, "vol": 0.022},
    {"name": "SK Hynix", "ticker": "000660.KS", "cur": "KRW", "mkt": "Seoul", "theme": "Tech · AI / Semiconduttori (memorie)", "start": 205000, "drift": 0.0011, "vol": 0.024},
    {"name": "Taiwan Semiconductor", "ticker": "TSM", "cur": "USD", "mkt": "NYSE", "theme": "Tech · AI / Semiconduttori (foundry)", "start": 185, "drift": 0.001, "vol": 0.02},
    {"name": "JPMorgan", "ticker": "JPM", "cur": "USD", "mkt": "NYSE", "theme": "Finanza · Banche", "start": 205, "drift": 0.0005, "vol": 0.013},
    {"name": "Intesa Sanpaolo", "ticker": "ISP.MI", "cur": "EUR", "mkt": "Milano", "theme": "Finanza · Banche (Italia)", "start": 3.9, "drift": 0.0006, "vol": 0.014},
    {"name": "Italgas", "ticker": "IG.MI", "cur": "EUR", "mkt": "Milano", "theme": "Utility · Infrastrutture gas (Italia)", "start": 6.2, "drift": 0.0004, "vol": 0.011},
    {"name": "Eli Lilly", "ticker": "LLY", "cur": "USD", "mkt": "NYSE", "theme": "Salute · Farmaceutica", "start": 780, "drift": 0.0008, "vol": 0.018},
    {"name": "Novo Nordisk", "ticker": "NVO", "cur": "USD", "mkt": "NYSE", "theme": "Salute · Farmaceutica", "start": 128, "drift": -0.0002, "vol": 0.02},
    {"name": "LVMH", "ticker": "MC.PA", "cur": "EUR", "mkt": "Parigi", "theme": "Lusso · Beni voluttuari", "start": 640, "drift": -0.0001, "vol": 0.016},
    {"name": "Ferrari", "ticker": "RACE", "cur": "EUR", "mkt": "Milano", "theme": "Lusso · Auto (Italia)", "start": 420, "drift": 0.0007, "vol": 0.015},
]


def gen_series(spec: Dict, n: int = 320, seed: int = 0):
    rng = random.Random(seed)
    price = spec["start"]
    dates, o, h, l, c, v = [], [], [], [], [], []
    today = dt.date.today()
    day = today - dt.timedelta(days=int(n * 1.45))
    count = 0
    while count < n:
        if day.weekday() < 5:
            shock = rng.gauss(spec["drift"], spec["vol"])
            wave = 0.001 * math.sin(count / 20.0)
            open_p = price
            price = max(0.5, price * (1 + shock + wave))
            high_p = max(open_p, price) * (1 + abs(rng.gauss(0, 0.004)))
            low_p = min(open_p, price) * (1 - abs(rng.gauss(0, 0.004)))
            dates.append(day.strftime("%Y-%m-%d"))
            o.append(open_p); h.append(high_p); l.append(low_p); c.append(price)
            v.append(rng.uniform(5e6, 6e7))
            count += 1
        day += dt.timedelta(days=1)
    return dates, o, h, l, c, v


def main():
    out: List[Dict] = []
    for i, spec in enumerate(SEEDS):
        dates, o, h, l, c, v = gen_series(spec, seed=i + 11)
        price = c[-1]
        rng = random.Random(i + 100)
        # target analisti demo: dispersione realistica attorno al prezzo
        tilt = rng.uniform(-0.12, 0.22)
        target = round(price * (1 + tilt), 2)
        fund = {
            "pe": round(rng.uniform(14, 44), 2),
            "forward_pe": round(rng.uniform(12, 34), 2),
            "target_mean": target,
            "target_low": round(target * rng.uniform(0.78, 0.92), 2),
            "target_high": round(target * rng.uniform(1.08, 1.3), 2),
            "rating": rng.choice(["strong_buy", "buy", "buy", "hold"]),
            "n_analysts": rng.randint(18, 52),
            "currency": spec["cur"],
            "exchange": spec["mkt"],
        }
        out.append(stock_analysis.build_stock(
            spec["name"], spec["ticker"], spec["cur"], spec["mkt"], spec["theme"],
            dates, o, h, l, c, v, fundamentals=fund,
        ))

    out.sort(key=lambda s: s["score"], reverse=True)
    data = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "Dati dimostrativi (sintetici)",
        "demo": True,
        "count": len(out),
        "bullish_count": sum(1 for s in out if s["verdict"] == "Bullish"),
        "bearish_count": sum(1 for s in out if s["verdict"] == "Bearish"),
        "stocks": out,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Scritto seed demo titoli in {OUT} — {data['count']} titoli")


if __name__ == "__main__":
    main()
