"""
Motore di calcolo per indicatori tecnici.
Funzioni pure in Python standard (nessuna dipendenza esterna): lavorano su
liste di float, così possono essere usate sia dal fetcher reale (dati Yahoo)
sia dal generatore di dati demo.
"""
from __future__ import annotations

from typing import List, Optional


def sma(values: List[float], period: int) -> List[Optional[float]]:
    """Media mobile semplice. Ritorna una lista della stessa lunghezza,
    con None dove non ci sono abbastanza dati."""
    out: List[Optional[float]] = []
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out.append(running / period)
        else:
            out.append(None)
    return out


def ema(values: List[float], period: int) -> List[Optional[float]]:
    """Media mobile esponenziale."""
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    # seed con SMA dei primi `period` valori
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    """RSI con smoothing di Wilder."""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if n <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        ch = values[i] - values[i - 1]
        if ch >= 0:
            gains += ch
        else:
            losses -= ch
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from_avg(avg_gain, avg_loss)
    for i in range(period + 1, n):
        ch = values[i] - values[i - 1]
        gain = ch if ch > 0 else 0.0
        loss = -ch if ch < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi_from_avg(avg_gain, avg_loss)
    return out


def _rsi_from_avg(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD classico. Ritorna (macd_line, signal_line, histogram)."""
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line: List[Optional[float]] = []
    for f, s in zip(ema_fast, ema_slow):
        if f is None or s is None:
            macd_line.append(None)
        else:
            macd_line.append(f - s)
    # signal = EMA del macd_line (solo sulla parte valida)
    valid = [v for v in macd_line if v is not None]
    start = len(macd_line) - len(valid)
    sig_valid = ema(valid, signal)
    signal_line: List[Optional[float]] = [None] * len(macd_line)
    for i, v in enumerate(sig_valid):
        signal_line[start + i] = v
    hist: List[Optional[float]] = []
    for m, s in zip(macd_line, signal_line):
        if m is None or s is None:
            hist.append(None)
        else:
            hist.append(m - s)
    return macd_line, signal_line, hist


def bollinger(values: List[float], period: int = 20, mult: float = 2.0):
    """Bande di Bollinger. Ritorna (mid, upper, lower)."""
    mid = sma(values, period)
    upper: List[Optional[float]] = [None] * len(values)
    lower: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if i >= period - 1:
            window = values[i - period + 1 : i + 1]
            m = mid[i]
            std = (sum((x - m) ** 2 for x in window) / period) ** 0.5
            upper[i] = m + mult * std
            lower[i] = m - mult * std
    return mid, upper, lower


def pct_return(values: List[float], lookback: int) -> Optional[float]:
    """Rendimento percentuale rispetto a `lookback` barre fa."""
    if len(values) <= lookback or values[-lookback - 1] == 0:
        return None
    return (values[-1] / values[-lookback - 1] - 1) * 100


def last_valid(seq: List[Optional[float]]) -> Optional[float]:
    for v in reversed(seq):
        if v is not None:
            return v
    return None


def max_drawdown_from_high(values: List[float]) -> float:
    """Drawdown percentuale corrente rispetto al massimo del periodo."""
    if not values:
        return 0.0
    peak = max(values)
    if peak == 0:
        return 0.0
    return (values[-1] / peak - 1) * 100


def max_drawdown(values: List[float]) -> float:
    """Massimo drawdown del periodo: la peggior discesa picco-minimo
    (valore piu' negativo), in percentuale."""
    if len(values) < 2:
        return 0.0
    peak = values[0]
    mdd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak:
            dd = (v / peak - 1) * 100
            if dd < mdd:
                mdd = dd
    return mdd


def volume_profile(highs, lows, closes, volumes, lookback: int = 252,
                   bins: int = 50) -> Optional[dict]:
    """Profilo dei volumi su una finestra recente.

    Ritorna il POC (Point of Control = il prezzo con il maggior volume
    scambiato) e l'area di valore (la fascia di prezzo che contiene il ~70%
    del volume, costruita espandendosi dal POC). Ogni barra distribuisce il
    proprio volume in modo uniforme sui bin coperti dal suo range [low, high].
    """
    n = len(closes)
    if n == 0:
        return None
    s = max(0, n - lookback)
    H, L, V = highs[s:], lows[s:], volumes[s:]
    lo = min(x for x in L if x is not None)
    hi = max(x for x in H if x is not None)
    if not (hi > lo):
        return None
    width = (hi - lo) / bins
    prof = [0.0] * bins
    for h, l, v in zip(H, L, V):
        if v is None or v <= 0 or h is None or l is None:
            continue
        b0 = int((l - lo) / width)
        b1 = int((h - lo) / width)
        b0 = max(0, min(bins - 1, b0))
        b1 = max(0, min(bins - 1, b1))
        share = v / (b1 - b0 + 1)
        for b in range(b0, b1 + 1):
            prof[b] += share
    total = sum(prof)
    if total <= 0:
        return None
    poc_i = max(range(bins), key=lambda i: prof[i])
    poc = lo + (poc_i + 0.5) * width
    # area di valore: espandi dal POC finche' raccogli il 70% del volume
    target = total * 0.70
    acc = prof[poc_i]
    lo_i = hi_i = poc_i
    while acc < target and (lo_i > 0 or hi_i < bins - 1):
        left = prof[lo_i - 1] if lo_i > 0 else -1.0
        right = prof[hi_i + 1] if hi_i < bins - 1 else -1.0
        if right >= left:
            hi_i += 1
            acc += prof[hi_i]
        else:
            lo_i -= 1
            acc += prof[lo_i]
    return {
        "poc": round(poc, 2),
        "va_low": round(lo + lo_i * width, 2),
        "va_high": round(lo + (hi_i + 1) * width, 2),
        "lookback": min(lookback, n),
    }


def trend_structure(highs, lows, closes, k: int = 5, lookback: int = 126,
                    breakout_win: int = 63) -> Optional[dict]:
    """Struttura del trend basata sui punti di svolta (swing high/low).

    Individua i massimi e minimi relativi (pivot confermati da `k` barre per
    lato) e ne confronta gli ultimi due: massimi+minimi crescenti = rialzista,
    decrescenti = ribassista, altrimenti laterale/misto. Rileva inoltre la
    rottura (breakout) dei massimi/minimi delle ultime `breakout_win` sedute.
    Ritorna valori grezzi; i testi in italiano sono composti a valle.
    """
    n = len(closes)
    if n < max(30, 2 * k + 2):
        return None
    s = max(0, n - lookback)
    sh, sl = [], []   # swing highs / lows: (indice, prezzo)
    for i in range(max(s, k), n - k):
        seg_h = highs[i - k:i + k + 1]
        seg_l = lows[i - k:i + k + 1]
        if highs[i] is not None and highs[i] == max(x for x in seg_h if x is not None):
            sh.append((i, highs[i]))
        if lows[i] is not None and lows[i] == min(x for x in seg_l if x is not None):
            sl.append((i, lows[i]))

    hh = sh[-1][1] > sh[-2][1] if len(sh) >= 2 else None
    hl = sl[-1][1] > sl[-2][1] if len(sl) >= 2 else None
    if hh and hl:
        trend = "up"
    elif hh is False and hl is False:
        trend = "down"
    else:
        trend = "mixed"

    bs = max(0, n - breakout_win)
    prior_highs = [x for x in highs[bs:n - 1] if x is not None]
    prior_lows = [x for x in lows[bs:n - 1] if x is not None]
    prior_high = max(prior_highs) if prior_highs else highs[-1]
    prior_low = min(prior_lows) if prior_lows else lows[-1]
    close = closes[-1]
    breakout = None
    if close >= prior_high:
        breakout = "up"
    elif close <= prior_low:
        breakout = "down"

    # resistenza = swing high piu' vicino SOPRA il prezzo; supporto = swing low
    # piu' vicino SOTTO il prezzo (garantisce supporto <= prezzo <= resistenza)
    res_above = [p for _, p in sh if p >= close]
    sup_below = [p for _, p in sl if p <= close]
    resistance = min(res_above) if res_above else max(prior_high, close)
    support = max(sup_below) if sup_below else min(prior_low, close)
    return {
        "trend": trend,
        "resistance": round(resistance, 2),
        "support": round(support, 2),
        "breakout": breakout,
        "breakout_high": round(prior_high, 2),
        "breakout_low": round(prior_low, 2),
        "n_highs": len(sh),
        "n_lows": len(sl),
    }


# ---------------------------------------------------------------------------
# ANALISI VOLUMETRICA AVANZATA (Volume Profile, inefficienze, momentum)
# ---------------------------------------------------------------------------

def _profile(highs, lows, volumes, lo, hi, bins):
    """Distribuisce il volume di ogni barra sui bin coperti da [low, high]."""
    width = (hi - lo) / bins
    prof = [0.0] * bins
    for h, l, v in zip(highs, lows, volumes):
        if v is None or v <= 0 or h is None or l is None:
            continue
        b0 = max(0, min(bins - 1, int((l - lo) / width)))
        b1 = max(0, min(bins - 1, int((h - lo) / width)))
        share = v / (b1 - b0 + 1)
        for b in range(b0, b1 + 1):
            prof[b] += share
    return prof, width


def _poc_of(highs, lows, volumes, bins=40):
    hs = [x for x in highs if x is not None]
    ls = [x for x in lows if x is not None]
    if not hs or not ls:
        return None
    lo, hi = min(ls), max(hs)
    if not (hi > lo):
        return None
    prof, width = _profile(highs, lows, volumes, lo, hi, bins)
    if sum(prof) <= 0:
        return None
    i = max(range(bins), key=lambda k: prof[k])
    return lo + (i + 0.5) * width


def hvn_nodes(highs, lows, volumes, lookback=252, bins=50, top_n=3, gap=3):
    """Aree ad alto volume ('malloppi') oltre il POC: i massimi locali del
    profilo, distanti almeno `gap` bin dal POC e tra loro."""
    if not highs:
        return []
    s = max(0, len(highs) - lookback)
    H, L, V = highs[s:], lows[s:], volumes[s:]
    hs = [x for x in H if x is not None]
    ls = [x for x in L if x is not None]
    if not hs or not ls:
        return []
    lo, hi = min(ls), max(hs)
    if not (hi > lo):
        return []
    prof, width = _profile(H, L, V, lo, hi, bins)
    if sum(prof) <= 0:
        return []
    poc_i = max(range(bins), key=lambda k: prof[k])
    # massimi locali
    peaks = []
    for i in range(1, bins - 1):
        if prof[i] >= prof[i - 1] and prof[i] >= prof[i + 1] and abs(i - poc_i) >= gap:
            peaks.append((prof[i], i))
    peaks.sort(reverse=True)
    out, used = [], []
    for _, i in peaks:
        if all(abs(i - u) >= gap for u in used):
            out.append(round(lo + (i + 0.5) * width, 2))
            used.append(i)
        if len(out) >= top_n:
            break
    return out


def poc_migration(highs, lows, volumes, recent=63, older=189):
    """Confronta il POC recente con quello del periodo precedente: uno
    spostamento verso i minimi suggerisce accumulo ('alberello')."""
    n = len(highs)
    if n < recent + 40:
        return None
    poc_r = _poc_of(highs[n - recent:], lows[n - recent:], volumes[n - recent:])
    o0 = max(0, n - older)
    poc_o = _poc_of(highs[o0:n - recent], lows[o0:n - recent], volumes[o0:n - recent])
    if poc_r is None or poc_o is None:
        return None
    ratio = poc_r / poc_o - 1
    if ratio <= -0.02:
        direction = "verso_minimi"
    elif ratio >= 0.02:
        direction = "verso_massimi"
    else:
        direction = "stabile"
    return {"dir": direction, "poc_recent": round(poc_r, 2),
            "poc_old": round(poc_o, 2), "shift_pct": round(ratio * 100, 1)}


def _resample(dates, opens, highs, lows, closes, period):
    """Aggrega le barre giornaliere in settimanali ('W') o mensili ('M')."""
    import datetime as _dt
    buckets = {}
    order = []
    for i, d in enumerate(dates):
        try:
            dt = _dt.date.fromisoformat(d[:10])
        except Exception:  # noqa: BLE001
            continue
        if period == "W":
            iso = dt.isocalendar()
            key = (iso[0], iso[1])
        else:
            key = (dt.year, dt.month)
        if key not in buckets:
            buckets[key] = {"o": opens[i], "h": highs[i], "l": lows[i], "c": closes[i]}
            order.append(key)
        else:
            b = buckets[key]
            b["h"] = max(b["h"], highs[i])
            b["l"] = min(b["l"], lows[i])
            b["c"] = closes[i]
    o = [buckets[k]["o"] for k in order]
    h = [buckets[k]["h"] for k in order]
    l = [buckets[k]["l"] for k in order]
    c = [buckets[k]["c"] for k in order]
    return o, h, l, c


def open_fvgs(highs, lows, closes, max_out=2):
    """Inefficienze di prezzo (Fair Value Gap a 3 barre) ancora aperte.
    Bullish: low[i] > high[i-2]; bearish: high[i] < low[i-2].
    Restituisce le piu' vicine al prezzo attuale, non ancora riempite."""
    n = len(closes)
    if n < 3:
        return []
    price = closes[-1]
    gaps = []
    for i in range(2, n):
        if lows[i] > highs[i - 2]:
            g_lo, g_hi, d = highs[i - 2], lows[i], "bull"
        elif highs[i] < lows[i - 2]:
            g_lo, g_hi, d = highs[i], lows[i - 2], "bear"
        else:
            continue
        # ancora aperta se il prezzo successivo non l'ha riempita
        filled = any(lows[j] <= g_lo and highs[j] >= g_hi for j in range(i + 1, n))
        # oppure parzialmente attraversata: consideriamo chiusa se il prezzo
        # e' rientrato oltre meta' del gap
        mid = (g_lo + g_hi) / 2
        crossed = any(lows[j] <= mid <= highs[j] for j in range(i + 1, n))
        if filled or crossed:
            continue
        gaps.append({"dir": d, "lo": round(g_lo, 2), "hi": round(g_hi, 2),
                     "above": g_lo > price, "dist": abs((g_lo + g_hi) / 2 - price)})
    gaps.sort(key=lambda g: g["dist"])
    for g in gaps:
        g.pop("dist", None)
    return gaps[:max_out]


def momentum_quality(closes, lookback=63):
    """Qualita' dell'uscita dai minimi: impulsiva ('missile') vs lenta/
    inclinata ('morbido')."""
    n = len(closes)
    if n < 10:
        return None
    s = max(0, n - lookback)
    window = closes[s:]
    i_low = min(range(len(window)), key=lambda k: window[k])
    seg = window[i_low:]
    bars = len(seg) - 1
    if bars < 3 or seg[0] == 0:
        return {"type": "laterale", "gain": 0.0, "bars": bars, "from_low": round(window[i_low], 2)}
    gain = (seg[-1] / seg[0] - 1) * 100
    # R^2 di una regressione lineare su seg
    m = len(seg)
    xs = list(range(m))
    mx = sum(xs) / m
    my = sum(seg) / m
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((xs[k] - mx) * (seg[k] - my) for k in range(m))
    syy = sum((y - my) ** 2 for y in seg)
    r2 = (sxy * sxy / (sxx * syy)) if sxx > 0 and syy > 0 else 0.0
    if gain >= 12 and r2 >= 0.80:
        typ = "missile"
    elif gain >= 4:
        typ = "morbido"
    else:
        typ = "laterale"
    return {"type": typ, "gain": round(gain, 1), "bars": bars,
            "r2": round(r2, 2), "from_low": round(window[i_low], 2)}


def volatility_compression(closes, short=20, long=100):
    """Compressione di volatilita': deviazione std recente vs storica."""
    def stdev_ret(vals):
        rets = [(vals[i] / vals[i - 1] - 1) for i in range(1, len(vals)) if vals[i - 1]]
        if len(rets) < 2:
            return None
        mu = sum(rets) / len(rets)
        return (sum((r - mu) ** 2 for r in rets) / len(rets)) ** 0.5
    if len(closes) < long + 1:
        return None
    sv = stdev_ret(closes[-short - 1:])
    lv = stdev_ret(closes[-long - 1:])
    if not sv or not lv or lv == 0:
        return None
    ratio = sv / lv
    return {"compressed": ratio < 0.75, "ratio": round(ratio, 2)}
