"""
Costruisce il record compatto di analisi per un singolo titolo a partire dalla
serie dei prezzi e dai dati fondamentali/analisti (quando disponibili).

Produce: segnale operativo (Compra/Mantieni/Vendi), punteggio tecnico,
sentiment, fair value (target analisti) con upside, indicatori chiave e
sparkline. Nessun dato di storico completo (per tenere leggero stocks.json).

Disclaimer: analisi automatica a scopo informativo, NON consulenza finanziaria.
Il "fair value" e' il target di consenso degli analisti (Yahoo Finance), non
una valutazione intrinseca proprietaria.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import indicators as ind


def build_stock(
    symbol: str,
    name: str,
    closes: List[float],
    fundamentals: Optional[Dict] = None,
    news: Optional[List[Dict]] = None,
) -> Dict:
    f = fundamentals or {}
    price = closes[-1]
    prev = closes[-2] if len(closes) > 1 else price
    change_pct = ((price - prev) / prev * 100) if prev else 0.0

    sma50 = ind.last_valid(ind.sma(closes, 50))
    sma200 = ind.last_valid(ind.sma(closes, 200))
    rsi = ind.last_valid(ind.rsi(closes, 14))
    _, _, hist = ind.macd(closes)
    macd_hist = ind.last_valid(hist)
    ret_1m = ind.pct_return(closes, 21)
    ret_3m = ind.pct_return(closes, 63)

    # ---- punteggio tecnico 0..100 ----
    score = 50.0
    if sma50 is not None:
        score += 8 if price > sma50 else -8
    if sma200 is not None:
        score += 12 if price > sma200 else -12
    if sma50 is not None and sma200 is not None:
        score += 8 if sma50 > sma200 else -8
    if macd_hist is not None:
        score += 7 if macd_hist > 0 else -7
    if ret_1m is not None:
        score += 6 if ret_1m > 0 else -6
    if rsi is not None:
        if rsi >= 70:
            score -= 4
        elif 50 <= rsi < 70:
            score += 4
        elif rsi <= 30:
            score += 2  # possibile rimbalzo da ipervenduto
    score = max(0.0, min(100.0, score))

    if score >= 62:
        signal = "Compra"
    elif score <= 40:
        signal = "Vendi"
    else:
        signal = "Mantieni"

    # ---- fair value / target analisti ----
    target = f.get("target_mean")
    upside = None
    if target and price:
        upside = (target / price - 1) * 100

    # ---- sentiment: tecnico + consenso analisti ----
    reco = f.get("reco_key")  # strong_buy/buy/hold/sell/strong_sell
    sentiment = _sentiment(score, reco, upside)

    return {
        "symbol": symbol,
        "name": name,
        "price": round(price, 2),
        "change_pct": round(change_pct, 2),
        "signal": signal,
        "score": round(score, 0),
        "sentiment": sentiment,
        "rsi": round(rsi, 0) if rsi is not None else None,
        "above_sma50": (price > sma50) if sma50 is not None else None,
        "above_sma200": (price > sma200) if sma200 is not None else None,
        "macd_bull": (macd_hist > 0) if macd_hist is not None else None,
        "ret_1m": round(ret_1m, 1) if ret_1m is not None else None,
        "ret_3m": round(ret_3m, 1) if ret_3m is not None else None,
        "fair_value": round(target, 2) if target else None,
        "upside": round(upside, 1) if upside is not None else None,
        "reco": reco,
        "num_analysts": f.get("num_analysts"),
        "pe": round(f["pe"], 1) if f.get("pe") else None,
        "market_cap": f.get("market_cap"),
        "div_yield": round(f["div_yield"], 2) if f.get("div_yield") else None,
        "sparkline": [round(c, 2) for c in closes[-32:]],
        "news": news or [],
    }


def _sentiment(score: float, reco: Optional[str], upside: Optional[float]) -> str:
    pts = 0
    # componente tecnica
    if score >= 60:
        pts += 1
    elif score <= 42:
        pts -= 1
    # consenso analisti
    if reco in ("strong_buy", "buy"):
        pts += 1
    elif reco in ("sell", "strong_sell"):
        pts -= 1
    # upside vs target
    if upside is not None:
        if upside > 10:
            pts += 1
        elif upside < -5:
            pts -= 1
    if pts >= 2:
        return "Positivo"
    if pts <= -1:
        return "Negativo"
    return "Neutro"


def summary(stocks: List[Dict]) -> Dict:
    buy = sum(1 for s in stocks if s["signal"] == "Compra")
    hold = sum(1 for s in stocks if s["signal"] == "Mantieni")
    sell = sum(1 for s in stocks if s["signal"] == "Vendi")
    ups = [s["upside"] for s in stocks if s.get("upside") is not None]
    avg_upside = sum(ups) / len(ups) if ups else None
    pos = sum(1 for s in stocks if s["sentiment"] == "Positivo")
    neg = sum(1 for s in stocks if s["sentiment"] == "Negativo")
    # breadth: quanti sopra la SMA200
    above = [s for s in stocks if s.get("above_sma200")]
    breadth = len(above) / len(stocks) * 100 if stocks else 0
    return {
        "count": len(stocks),
        "buy": buy, "hold": hold, "sell": sell,
        "avg_upside": round(avg_upside, 1) if avg_upside is not None else None,
        "positive": pos, "negative": neg,
        "breadth_above_sma200": round(breadth, 0),
    }
