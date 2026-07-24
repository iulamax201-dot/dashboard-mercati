"""
Genera un docs/data.json DIMOSTRATIVO senza accesso a internet, così che la
dashboard mostri qualcosa al primo caricamento (prima che GitHub Actions
esegua il primo aggiornamento reale).

I dati sono sintetici e chiaramente marcati come "demo". Verranno sostituiti
da dati reali al primo run del workflow.

Uso:
    python scripts/seed_data.py
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
import analysis  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "data.json")

# valori di partenza realistici (livelli approssimativi degli indici)
SEEDS = [
    {"name": "S&P 500", "symbol": "^GSPC", "start": 4800, "drift": 0.00035, "vol": 0.009, "etf": "SPY"},
    {"name": "Dow Jones", "symbol": "^DJI", "start": 38000, "drift": 0.00025, "vol": 0.008, "etf": "DIA"},
    {"name": "Nasdaq", "symbol": "^IXIC", "start": 15200, "drift": 0.00045, "vol": 0.012, "etf": "QQQ"},
]


def gen_series(spec: Dict, n: int = 320, seed: int = 0):
    rng = random.Random(seed)
    price = spec["start"]
    dates, o, h, l, c, v = [], [], [], [], [], []
    today = dt.date.today()
    # genera all'indietro per avere date di trading (salta i weekend)
    day = today - dt.timedelta(days=int(n * 1.45))
    count = 0
    while count < n:
        if day.weekday() < 5:  # lun-ven
            shock = rng.gauss(spec["drift"], spec["vol"])
            # leggera stagionalità/ondulazione per un grafico credibile
            wave = 0.0006 * math.sin(count / 18.0)
            open_p = price
            price = price * (1 + shock + wave)
            high_p = max(open_p, price) * (1 + abs(rng.gauss(0, 0.003)))
            low_p = min(open_p, price) * (1 - abs(rng.gauss(0, 0.003)))
            dates.append(day.strftime("%Y-%m-%d"))
            o.append(open_p); h.append(high_p); l.append(low_p); c.append(price)
            v.append(rng.uniform(2.5e9, 5e9))
            count += 1
        day += dt.timedelta(days=1)
    return dates, o, h, l, c, v


def main():
    indices_out: List[Dict] = []
    for i, spec in enumerate(SEEDS):
        dates, o, h, l, c, v = gen_series(spec, seed=i + 7)
        fund = {
            "proxy_etf": spec["etf"],
            "pe": round(random.uniform(19, 29), 2),
            "yield": round(random.uniform(0.5, 2.0), 2),
            "beta": 1.0,
            "note": "valori dimostrativi",
        }
        ath = max(c) * random.uniform(1.0, 1.08)  # record poco sopra
        news = [
            {"title": f"{spec['name']}: sintesi dimostrativa dei mercati",
             "publisher": "Demo", "link": "",
             "date": dt.date.today().isoformat() + " 09:00"},
            {"title": "Fattori macro e trimestrali in focus (esempio)",
             "publisher": "Demo", "link": "",
             "date": dt.date.today().isoformat() + " 08:30"},
        ]
        indices_out.append(
            analysis.build_index_analysis(
                spec["name"], spec["symbol"], dates, o, h, l, c, v,
                fundamentals=fund, ath=ath, news=news,
            )
        )

    data = {
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "Dati dimostrativi (sintetici)",
        "demo": True,
        "market": analysis.market_summary(indices_out),
        "indices": indices_out,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Scritto seed demo in {OUT} — fase: {data['market']['phase']}")


if __name__ == "__main__":
    main()
