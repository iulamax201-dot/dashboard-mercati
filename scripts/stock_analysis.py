"""
Analisi per singolo titolo azionario: verdetto tecnico (Bullish/Neutrale/
Bearish) con punteggio motivato, indicazione operativa ("quando ha senso
comprare o meno") e stima di fair value basata sui target degli analisti
(Yahoo) e sui multipli di valutazione (P/E).

NB: solo scopo informativo/educativo, NON consulenza finanziaria. Il fair
value riflette il consenso degli analisti, che può sbagliare.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import indicators as ind

RATING_IT = {
    "strong_buy": "Strong Buy", "buy": "Buy", "hold": "Hold",
    "underperform": "Underperform", "sell": "Sell", "none": "—",
}


def _r(v: Optional[float], nd: int = 2) -> Optional[float]:
    return round(v, nd) if v is not None else None


def compute_fair_value(price: float, fund: Optional[Dict]) -> Dict:
    """Fair value dai target degli analisti + contesto di valutazione (P/E)."""
    fund = fund or {}
    out: Dict = {
        "pe": fund.get("pe"),
        "forward_pe": fund.get("forward_pe"),
        "rating": RATING_IT.get((fund.get("rating") or "none"), fund.get("rating")),
        "n_analysts": fund.get("n_analysts"),
    }
    target = fund.get("target_mean")
    if target and price:
        upside = (target / price - 1) * 100
        out.update({
            "target": round(target, 2),
            "target_low": _r(fund.get("target_low")),
            "target_high": _r(fund.get("target_high")),
            "upside_pct": round(upside, 1),
        })
        if upside >= 15:
            lab, lv = "Sottovalutato", "pos"
        elif upside >= 5:
            lab, lv = "Sotto il fair value", "pos"
        elif upside > -5:
            lab, lv = "In linea col fair value", "warn"
        elif upside > -15:
            lab, lv = "Sopra il fair value", "neg"
        else:
            lab, lv = "Sopravvalutato", "neg"
        out["label"], out["level"] = lab, lv
    else:
        out["label"], out["level"] = "Fair value non disponibile", "warn"
    return out


def _stock_action(verdict: str, rsi: Optional[float], fair: Dict) -> Dict:
    """Indicazione operativa sintetica combinando trend, RSI e valutazione.
    NON è consulenza finanziaria."""
    up = fair.get("upside_pct")
    if verdict == "Bullish":
        if rsi is not None and rsi >= 72:
            return {"stance": "Comprare con cautela", "level": "warn",
                    "text": "Trend forte ma ipercomprato (RSI alto): meglio non inseguire il "
                    "rialzo e attendere un ritracciamento verso la media a 50 giorni."}
        if up is not None and up <= -10:
            return {"stance": "Trend ok, ma prezzo caro", "level": "warn",
                    "text": "Momentum positivo ma la quotazione è sopra il fair value degli "
                    "analisti: rapporto rischio/rendimento meno favorevole agli acquisti."}
        extra = " e prezzo interessante rispetto al fair value" if (up or 0) >= 5 else ""
        return {"stance": "Impostazione favorevole", "level": "pos",
                "text": "Trend costruttivo" + extra + ": contesto tendenzialmente favorevole; "
                "ingressi preferibili sulle debolezze, verso le medie mobili."}
    if verdict == "Bearish":
        if up is not None and up >= 15:
            return {"stance": "Possibile occasione, ma cautela", "level": "warn",
                    "text": "Trend debole ma quota molto sotto il fair value: eventuale ingresso "
                    "graduale solo dopo segnali di stabilizzazione del prezzo."}
        return {"stance": "Meglio attendere", "level": "neg",
                "text": "Trend debole/ribassista: preferibile evitare nuovi acquisti finché non "
                "recupera le medie a 50 e 200 giorni."}
    return {"stance": "Attendere conferma", "level": "warn",
            "text": "Fase laterale/incerta: conviene attendere una direzione più chiara di "
            "prezzo e medie mobili prima di muoversi."}


def build_stock(
    name: str,
    ticker: str,
    currency: str,
    market: str,
    theme: str,
    dates: List[str],
    opens: List[float],
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    fundamentals: Optional[Dict] = None,
) -> Dict:
    fund = fundamentals or {}
    sma50 = ind.sma(closes, 50)
    sma200 = ind.sma(closes, 200)
    rsi14 = ind.rsi(closes, 14)
    macd_line, signal_line, hist = ind.macd(closes)

    price = closes[-1]
    prev = closes[-2] if len(closes) > 1 else price
    change = price - prev
    change_pct = (change / prev * 100) if prev else 0.0

    v50 = ind.last_valid(sma50)
    v200 = ind.last_valid(sma200)
    vrsi = ind.last_valid(rsi14)
    vhist = ind.last_valid(hist)
    golden = v50 is not None and v200 is not None and v50 > v200

    high52 = max(closes[-252:]) if closes else price
    low52 = min(closes[-252:]) if closes else price
    dd = ind.max_drawdown_from_high(closes[-252:])

    ret_1w = ind.pct_return(closes, 5)
    ret_1m = ind.pct_return(closes, 21)
    ret_3m = ind.pct_return(closes, 63)
    ret_6m = ind.pct_return(closes, 126)
    ret_1y = ind.pct_return(closes, 252)

    # ---------- VERDETTO (punteggio 0..100) ----------
    score = 50.0
    reasons: List[Dict] = []

    def add(cond: bool, w: float, pos: str, neg: str):
        nonlocal score
        if cond:
            score += w
            reasons.append({"sentiment": "bull", "text": pos})
        else:
            score -= w
            reasons.append({"sentiment": "bear", "text": neg})

    if v50 is not None:
        add(price > v50, 8, "Sopra la media a 50 giorni", "Sotto la media a 50 giorni")
    if v200 is not None:
        add(price > v200, 12,
            "Sopra la media a 200 giorni (trend di lungo positivo)",
            "Sotto la media a 200 giorni (trend di lungo negativo)")
    if v50 is not None and v200 is not None:
        add(golden, 10, "Golden cross (SMA50 sopra SMA200)", "Death cross (SMA50 sotto SMA200)")
    if vhist is not None:
        add(vhist > 0, 8, "MACD positivo (momentum al rialzo)", "MACD negativo (momentum al ribasso)")
    if ret_1m is not None:
        add(ret_1m > 0, 6, "Rendimento a 1 mese positivo", "Rendimento a 1 mese negativo")
    if vrsi is not None:
        if vrsi >= 70:
            score -= 4
            reasons.append({"sentiment": "warn", "text": f"RSI ipercomprato ({vrsi:.0f})"})
        elif vrsi <= 30:
            score -= 2
            reasons.append({"sentiment": "warn", "text": f"RSI ipervenduto ({vrsi:.0f})"})
        elif 50 <= vrsi < 70:
            score += 4
            reasons.append({"sentiment": "bull", "text": f"RSI in zona di forza ({vrsi:.0f})"})
        else:
            reasons.append({"sentiment": "neutral", "text": f"RSI neutrale ({vrsi:.0f})"})

    score = max(0.0, min(100.0, score))
    if score >= 62:
        verdict = "Bullish"
    elif score <= 42:
        verdict = "Bearish"
    else:
        verdict = "Neutrale"

    fair = compute_fair_value(price, fund)
    action = _stock_action(verdict, vrsi, fair)

    # POC / area di valore (profilo dei volumi sull'ultimo anno)
    poc = ind.volume_profile(highs, lows, closes, volumes, lookback=252, bins=50)

    hist_len = min(len(closes), 520)
    s = len(closes) - hist_len

    return {
        "name": name,
        "ticker": ticker,
        "currency": currency,
        "market": market,
        "theme": theme,
        "price": round(price, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "verdict": verdict,
        "score": round(score, 1),
        "reasons": reasons,
        "action": action,
        "fair_value": fair,
        "poc": poc,
        "technical": {
            "rsi": _r(vrsi),
            "sma50": _r(v50),
            "sma200": _r(v200),
            "macd_hist": _r(vhist, 3),
            "golden_cross": golden,
            "high_52w": round(high52, 2),
            "low_52w": round(low52, 2),
            "drawdown": round(dd, 2),
        },
        "returns": {
            "w1": _r(ret_1w), "m1": _r(ret_1m), "m3": _r(ret_3m),
            "m6": _r(ret_6m), "y1": _r(ret_1y),
        },
        "series": {
            "dates": dates[s:],
            "close": [round(c, 2) for c in closes[s:]],
            "sma50": [_r(x) for x in sma50[s:]],
            "sma200": [_r(x) for x in sma200[s:]],
        },
    }
