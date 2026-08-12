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


def _trend_block(raw: Optional[Dict], currency: str) -> Optional[Dict]:
    """Compone la descrizione in italiano della struttura del trend."""
    if not raw:
        return None
    sup, res = raw["support"], raw["resistance"]
    trend = raw["trend"]
    if trend == "up":
        label, bias, level = "Massimi e minimi crescenti", "Rialzista", "pos"
        text = (f"Struttura rialzista: la sequenza segna massimi e minimi crescenti. "
                f"L'impostazione resta positiva finché tiene il supporto (~{fmt_num(sup)}); "
                f"resistenza di riferimento a ~{fmt_num(res)}.")
    elif trend == "down":
        label, bias, level = "Massimi e minimi decrescenti", "Ribassista", "neg"
        text = (f"Struttura ribassista: massimi e minimi decrescenti. Serve superare la "
                f"resistenza (~{fmt_num(res)}) per invertire; sotto il supporto (~{fmt_num(sup)}) "
                f"la debolezza si aggrava.")
    else:
        label, bias, level = "Struttura laterale / mista", "Neutrale", "warn"
        text = (f"Nessuna sequenza netta di massimi e minimi: fase laterale/incerta. "
                f"Rottura sopra ~{fmt_num(res)} = segnale di forza, sotto ~{fmt_num(sup)} = debolezza.")

    breakout = None
    if raw["breakout"] == "up":
        breakout = {"dir": "up",
                    "text": f"Breakout rialzista: nuovi massimi di periodo (sopra ~{fmt_num(raw['breakout_high'])})."}
    elif raw["breakout"] == "down":
        breakout = {"dir": "down",
                    "text": f"Breakout ribassista: nuovi minimi di periodo (sotto ~{fmt_num(raw['breakout_low'])})."}

    return {"label": label, "bias": bias, "level": level, "text": text,
            "support": sup, "resistance": res, "breakout": breakout}


def fmt_num(v: Optional[float]) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace(",", ".")
    return f"{v:.2f}".rstrip("0").rstrip(".") if v == int(v) else f"{v:.2f}"


def _volumetric(dates, opens, highs, lows, closes, volumes, currency, poc_dict):
    """Report di analisi volumetrica (Volume Profile, inefficienze, momentum,
    piano frazionato) secondo la metodologia richiesta. Solo scopo educativo."""
    if not poc_dict or len(closes) < 60:
        return None
    price = closes[-1]
    poc = poc_dict["poc"]
    va_lo, va_hi = poc_dict["va_low"], poc_dict["va_high"]

    def m(v):
        return fmt_num(v) + " " + currency

    mig = ind.poc_migration(highs, lows, volumes)
    hvn = ind.hvn_nodes(highs, lows, volumes)
    comp = ind.volatility_compression(closes)
    mom = ind.momentum_quality(closes)
    ow, oh, ol, oc = ind._resample(dates, opens, highs, lows, closes, "W")
    om, omh, oml, omc = ind._resample(dates, opens, highs, lows, closes, "M")
    fvg_w = ind.open_fvgs(oh, ol, oc)
    fvg_m = ind.open_fvgs(omh, oml, omc)

    # ---- 1. Quadro Volumetrico & POC ----
    s1 = []
    s1.append(f"POC (Point of Control) a {m(poc)}; prezzo attualmente "
              f"{'sopra' if price >= poc else 'sotto'} l'area di controllo "
              f"(area di valore {m(va_lo)} – {m(va_hi)}).")
    if mig:
        if mig["dir"] == "verso_minimi":
            s1.append(f"Migrazione del POC verso i minimi ({mig['shift_pct']}%): possibile "
                      f"accumulo istituzionale in profondità (“alberello”).")
        elif mig["dir"] == "verso_massimi":
            s1.append(f"Migrazione del POC verso i massimi (+{mig['shift_pct']}%): i volumi si "
                      f"spostano in alto, tipico delle fasi mature/distribuzione.")
        else:
            s1.append("POC sostanzialmente stabile: volumi bilanciati, nessuna migrazione netta.")
    if hvn:
        s1.append("Aree ad alto volume (“malloppi”) di riferimento a " +
                  ", ".join(m(x) for x in hvn) + " — supporti/resistenze volumetriche.")
    else:
        s1.append("Nessun “malloppo” secondario rilevante oltre il POC.")

    # ---- 2. Struttura di Prezzo ----
    s2 = []
    if comp:
        if comp["compressed"]:
            s2.append(f"Compressione di volatilità in atto (volatilità recente al {comp['ratio']}× "
                      f"della media): possibile base/rounding prima di un'espansione.")
        else:
            s2.append(f"Volatilità nella norma ({comp['ratio']}× della media): nessuna "
                      f"compressione evidente.")
    if mom:
        if mom["type"] == "missile":
            s2.append(f"Uscita dai minimi impulsiva (“a missile”): +{mom['gain']}% dal minimo "
                      f"di periodo con avanzata pulita — momentum di qualità.")
        elif mom["type"] == "morbido":
            s2.append(f"Avanzata lenta/inclinata (“morbida”): +{mom['gain']}% dal minimo ma senza "
                      f"impulso netto — attenzione a possibili flag di continuazione ribassista.")
        else:
            s2.append("Nessun movimento direzionale netto dai minimi recenti: fase laterale.")

    def _fvg_line(g, tf):
        d = "rialzista" if g["dir"] == "bull" else "ribassista"
        pos = "sopra" if g["above"] else "sotto"
        return f"Inefficienza {d} {tf} aperta a {m(g['lo'])} – {m(g['hi'])} ({pos} il prezzo)."
    if fvg_w or fvg_m:
        for g in fvg_w:
            s2.append(_fvg_line(g, "settimanale"))
        for g in fvg_m:
            s2.append(_fvg_line(g, "mensile"))
    else:
        s2.append("Nessuna inefficienza settimanale/mensile aperta rilevante.")

    # ---- 3. Invalidation & Target ----
    s3 = []
    inval = va_lo if va_lo < price else (mom["from_low"] if mom and mom["from_low"] < price
                                         else round(price * 0.95, 2))
    s3.append(f"Invalidazione sotto {m(inval)}: la perdita dell'area di valore/POC farebbe "
              f"decadere l'impostazione rialzista.")
    above = sorted({x for x in (hvn + [va_hi]) if x > price})
    for g in fvg_w + fvg_m:
        if g["above"]:
            above.append(g["lo"])
    above = sorted(set(above))[:3]
    if above:
        s3.append("Target volumetrici (per le prese di beneficio) verso " +
                  ", ".join(m(x) for x in above) +
                  " e chiusura delle eventuali inefficienze aperte sopra.")
    else:
        s3.append("Prezzo in territorio di scoperta: poche resistenze volumetriche sopra, "
                  "target sulle estensioni/livelli psicologici.")

    # ---- 4. Piano Operativo Frazionato ----
    ref_res = above[0] if above else None
    s4 = []
    if ref_res:
        s4.append(f"Tranche 1/3 sulla rottura confermata sopra {m(ref_res)} (candela piena ed "
                  f"estesa, non un semplice rigetto in resistenza).")
        s4.append(f"Tranche 2/3–3/3 sul retest dell'area POC ({m(poc)}) o della neckline "
                  f"appena superata.")
    else:
        s4.append(f"Con prezzo sopra le principali aree volumetriche, gestire eventuali "
                  f"aggiunte solo sui ritracciamenti verso il POC ({m(poc)}) o l'area di valore.")
    top_target = above[-1] if above else None
    if top_target:
        s4.append(f"Prese di beneficio (“pisaccata”) alla chiusura delle inefficienze "
                  f"settimanali/mensili o al test del POC maestro / resistenza superiore ({m(top_target)}).")
    else:
        s4.append("Prese di beneficio scalari sulle estensioni, alleggerendo sui primi segnali "
                  "di esaurimento del momentum.")

    return {
        "sections": [
            {"title": "Quadro Volumetrico & POC", "lines": s1},
            {"title": "Struttura di Prezzo", "lines": s2},
            {"title": "Punti di Invalidation & Target", "lines": s3},
            {"title": "Piano Operativo Frazionato", "lines": s4},
        ],
        "poc": poc, "va_low": va_lo, "va_high": va_hi,
        "invalidation": inval, "targets": above, "hvn": hvn,
    }


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

    # struttura del trend (swing high/low, breakout)
    structure = _trend_block(ind.trend_structure(highs, lows, closes), currency)

    # analisi volumetrica avanzata (Volume Profile, inefficienze, piano)
    volumetric = _volumetric(dates, opens, highs, lows, closes, volumes, currency, poc)

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
        "structure": structure,
        "volumetric": volumetric,
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
