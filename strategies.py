"""
strategies.py — All existing strategies preserved + enhanced
Includes: Candlestick patterns, MACD, RSI, VWAP, Bollinger, EMA, SLC
"""
import pandas as pd
import numpy as np


# ─── Helpers ──────────────────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period=14) -> float:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).iloc[-1]


def atr(bars: pd.DataFrame, period=14) -> float:
    high, low, close = bars['high'], bars['low'], bars['close']
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean().iloc[-1]


# ─── Candlestick Patterns ─────────────────────────────────────────────────────

def three_candle_bull(bars: pd.DataFrame) -> bool:
    if len(bars) < 3:
        return False
    c1, c2, c3 = bars.iloc[-3], bars.iloc[-2], bars.iloc[-1]
    all_green   = c1['close'] > c1['open'] and c2['close'] > c2['open'] and c3['close'] > c3['open']
    ascending   = c2['close'] > c1['close'] and c3['close'] > c2['close']
    min_body    = c3['close'] * 0.0005
    bodies_solid = (abs(c1['close']-c1['open']) >= min_body and
                    abs(c2['close']-c2['open']) >= min_body and
                    abs(c3['close']-c3['open']) >= min_body)
    return all_green and ascending and bodies_solid


def three_candle_bear(bars: pd.DataFrame) -> bool:
    if len(bars) < 3:
        return False
    c1, c2, c3 = bars.iloc[-3], bars.iloc[-2], bars.iloc[-1]
    all_red    = c1['close'] < c1['open'] and c2['close'] < c2['open'] and c3['close'] < c3['open']
    descending = c2['close'] < c1['close'] and c3['close'] < c2['close']
    min_body   = c3['close'] * 0.0005
    bodies_solid = (abs(c1['close']-c1['open']) >= min_body and
                    abs(c2['close']-c2['open']) >= min_body and
                    abs(c3['close']-c3['open']) >= min_body)
    return all_red and descending and bodies_solid


def candle_momentum_score(bars: pd.DataFrame) -> int:
    score = 0
    if three_candle_bull(bars):
        score += 3
    elif (len(bars) >= 2 and
          bars.iloc[-2]['close'] > bars.iloc[-2]['open'] and
          bars.iloc[-1]['close'] > bars.iloc[-1]['open'] and
          bars.iloc[-1]['close'] > bars.iloc[-2]['close']):
        score += 1
    if three_candle_bear(bars):
        score -= 3
    elif (len(bars) >= 2 and
          bars.iloc[-2]['close'] < bars.iloc[-2]['open'] and
          bars.iloc[-1]['close'] < bars.iloc[-1]['open'] and
          bars.iloc[-1]['close'] < bars.iloc[-2]['close']):
        score -= 1
    return score


def is_bullish_engulfing(bars: pd.DataFrame) -> bool:
    if len(bars) < 2: return False
    prev, curr = bars.iloc[-2], bars.iloc[-1]
    return (prev['close'] < prev['open'] and curr['close'] > curr['open'] and
            curr['open'] <= prev['close'] and curr['close'] >= prev['open'])


def is_bearish_engulfing(bars: pd.DataFrame) -> bool:
    if len(bars) < 2: return False
    prev, curr = bars.iloc[-2], bars.iloc[-1]
    return (prev['close'] > prev['open'] and curr['close'] < curr['open'] and
            curr['open'] >= prev['close'] and curr['close'] <= prev['open'])


def is_hammer(bars: pd.DataFrame) -> bool:
    if len(bars) < 1: return False
    c = bars.iloc[-1]
    body = abs(c['close'] - c['open'])
    lower_wick = min(c['open'], c['close']) - c['low']
    upper_wick = c['high'] - max(c['open'], c['close'])
    if body == 0: return False
    return lower_wick >= 2 * body and upper_wick <= 0.3 * body


def is_shooting_star(bars: pd.DataFrame) -> bool:
    if len(bars) < 1: return False
    c = bars.iloc[-1]
    body = abs(c['close'] - c['open'])
    upper_wick = c['high'] - max(c['open'], c['close'])
    lower_wick = min(c['open'], c['close']) - c['low']
    if body == 0: return False
    return upper_wick >= 2 * body and lower_wick <= 0.3 * body


def is_doji(bars: pd.DataFrame) -> bool:
    if len(bars) < 1: return False
    c = bars.iloc[-1]
    body = abs(c['close'] - c['open'])
    total_range = c['high'] - c['low']
    if total_range == 0: return False
    return body / total_range < 0.1


def is_morning_star(bars: pd.DataFrame) -> bool:
    if len(bars) < 3: return False
    c1, c2, c3 = bars.iloc[-3], bars.iloc[-2], bars.iloc[-1]
    big_red   = c1['close'] < c1['open'] and abs(c1['close']-c1['open']) > 0.5*(c1['high']-c1['low'])
    small_mid = abs(c2['close']-c2['open']) < abs(c1['close']-c1['open']) * 0.3
    big_green = c3['close'] > c3['open'] and c3['close'] > (c1['open']+c1['close'])/2
    return big_red and small_mid and big_green


def is_evening_star(bars: pd.DataFrame) -> bool:
    if len(bars) < 3: return False
    c1, c2, c3 = bars.iloc[-3], bars.iloc[-2], bars.iloc[-1]
    big_green = c1['close'] > c1['open'] and abs(c1['close']-c1['open']) > 0.5*(c1['high']-c1['low'])
    small_mid = abs(c2['close']-c2['open']) < abs(c1['close']-c1['open']) * 0.3
    big_red   = c3['close'] < c3['open'] and c3['close'] < (c1['open']+c1['close'])/2
    return big_green and small_mid and big_red


def candlestick_score(bars: pd.DataFrame) -> int:
    score = 0
    if is_bullish_engulfing(bars):  score += 2
    if is_hammer(bars):             score += 2
    if is_morning_star(bars):       score += 2
    if is_bearish_engulfing(bars):  score -= 2
    if is_shooting_star(bars):      score -= 2
    if is_evening_star(bars):       score -= 2
    return score


# ─── Technical Indicators ─────────────────────────────────────────────────────

def macd_signal(bars: pd.DataFrame):
    close = bars['close']
    macd_line   = ema(close, 12) - ema(close, 26)
    signal_line = ema(macd_line, 9)
    if macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-2] <= signal_line.iloc[-2]:
        return 'BUY'
    if macd_line.iloc[-1] < signal_line.iloc[-1] and macd_line.iloc[-2] >= signal_line.iloc[-2]:
        return 'SELL'
    return 'HOLD'


def vwap_signal(bars: pd.DataFrame) -> str:
    if 'volume' not in bars.columns or bars['volume'].sum() == 0:
        return 'HOLD'
    typical = (bars['high'] + bars['low'] + bars['close']) / 3
    vwap    = (typical * bars['volume']).cumsum() / bars['volume'].cumsum()
    price   = bars['close'].iloc[-1]
    if price > vwap.iloc[-1] * 1.001: return 'BUY'
    if price < vwap.iloc[-1] * 0.999: return 'SELL'
    return 'HOLD'


def bollinger_signal(bars: pd.DataFrame, period=20) -> str:
    if len(bars) < period: return 'HOLD'
    close = bars['close']
    mid   = close.rolling(period).mean()
    std   = close.rolling(period).std()
    if close.iloc[-1] <= (mid - 2*std).iloc[-1]: return 'BUY'
    if close.iloc[-1] >= (mid + 2*std).iloc[-1]: return 'SELL'
    return 'HOLD'


def ema_trend(bars: pd.DataFrame) -> str:
    if len(bars) < 21: return 'HOLD'
    close = bars['close']
    e9  = ema(close, 9).iloc[-1]
    e21 = ema(close, 21).iloc[-1]
    if e9 > e21: return 'BUY'
    if e9 < e21: return 'SELL'
    return 'HOLD'


# ─── NEW: Market Regime Detection ─────────────────────────────────────────────

def detect_market_regime(bars: pd.DataFrame) -> str:
    """
    Detect current market regime:
    - trending_up   : strong uptrend
    - trending_down : strong downtrend
    - ranging       : sideways / choppy
    - volatile      : high volatility, no clear direction
    """
    if len(bars) < 50:
        return 'unknown'

    close = bars['close']

    # ADX-like trend strength using EMA spread
    e20 = ema(close, 20).iloc[-1]
    e50 = ema(close, 50).iloc[-1]
    price = close.iloc[-1]

    # Volatility: ATR as % of price
    try:
        atr_val = atr(bars)
        vol_pct = atr_val / price * 100
    except:
        vol_pct = 1.0

    # Price vs EMAs
    above_e20 = price > e20
    above_e50 = price > e50
    ema_spread = abs(e20 - e50) / e50 * 100

    # Rolling returns for trend consistency
    returns = close.pct_change().tail(20)
    pos_days = (returns > 0).sum()
    neg_days = (returns < 0).sum()

    if vol_pct > 3.0:
        return 'volatile'
    elif ema_spread > 1.5 and above_e20 and above_e50 and pos_days >= 13:
        return 'trending_up'
    elif ema_spread > 1.5 and not above_e20 and not above_e50 and neg_days >= 13:
        return 'trending_down'
    else:
        return 'ranging'


# ─── NEW: Adaptive Signal based on regime ─────────────────────────────────────

def adaptive_signal(bars: pd.DataFrame, regime: str = None) -> dict:
    """
    Adjusts strategy weights based on market regime.
    - trending: favour momentum + EMA
    - ranging:  favour mean-reversion (Bollinger + RSI)
    - volatile: tighten thresholds, require higher score
    """
    if regime is None:
        regime = detect_market_regime(bars)

    score = 0
    weights = {
        'trending_up':   {'momentum': 3, 'macd': 3, 'ema': 2, 'vwap': 2, 'bollinger': 1, 'rsi': 1, 'candle': 2, 'threshold': 6},
        'trending_down': {'momentum': 3, 'macd': 3, 'ema': 2, 'vwap': 2, 'bollinger': 1, 'rsi': 1, 'candle': 2, 'threshold': 6},
        'ranging':       {'momentum': 1, 'macd': 1, 'ema': 1, 'vwap': 1, 'bollinger': 3, 'rsi': 3, 'candle': 2, 'threshold': 5},
        'volatile':      {'momentum': 2, 'macd': 2, 'ema': 2, 'vwap': 2, 'bollinger': 2, 'rsi': 2, 'candle': 2, 'threshold': 9},
        'unknown':       {'momentum': 2, 'macd': 2, 'ema': 1, 'vwap': 1, 'bollinger': 1, 'rsi': 2, 'candle': 2, 'threshold': 5},
    }
    w = weights.get(regime, weights['unknown'])

    mom = candle_momentum_score(bars)
    score += mom * w['momentum']

    cs = candlestick_score(bars)
    score += cs * w['candle']

    m = macd_signal(bars)
    if m == 'BUY':  score += w['macd']
    if m == 'SELL': score -= w['macd']

    v = vwap_signal(bars)
    if v == 'BUY':  score += w['vwap']
    if v == 'SELL': score -= w['vwap']

    b = bollinger_signal(bars)
    if b == 'BUY':  score += w['bollinger']
    if b == 'SELL': score -= w['bollinger']

    e = ema_trend(bars)
    if e == 'BUY':  score += w['ema']
    if e == 'SELL': score -= w['ema']

    r_val = 50
    try:
        r_val = rsi(bars['close'])
        if r_val < 35:   score += w['rsi'] * 2
        elif r_val < 45: score += w['rsi']
        elif r_val > 65: score -= w['rsi'] * 2
        elif r_val > 55: score -= w['rsi']
    except:
        pass

    threshold = w['threshold']
    signal = 'BUY' if score >= threshold else 'SELL' if score <= -threshold else 'HOLD'

    return {
        'signal':    signal,
        'score':     score,
        'regime':    regime,
        'threshold': threshold,
        'rsi':       round(r_val, 1),
        'macd':      m,
        'vwap':      v,
        'bollinger': b,
        'ema':       e,
    }


# ─── Combined Signal (original — preserved) ───────────────────────────────────

def combined_signal(bars: pd.DataFrame) -> str:
    if len(bars) < 26:
        return 'HOLD'
    score = 0
    score += candle_momentum_score(bars) * 2
    score += candlestick_score(bars) * 2
    m = macd_signal(bars)
    if m == 'BUY':  score += 2
    if m == 'SELL': score -= 2
    v = vwap_signal(bars)
    if v == 'BUY':  score += 1
    if v == 'SELL': score -= 1
    b = bollinger_signal(bars)
    if b == 'BUY':  score += 1
    if b == 'SELL': score -= 1
    e = ema_trend(bars)
    if e == 'BUY':  score += 1
    if e == 'SELL': score -= 1
    try:
        r = rsi(bars['close'])
        if r < 40:   score += 2
        elif r < 50: score += 1
        elif r > 60: score -= 2
        elif r > 50: score -= 1
    except:
        pass
    if score >= 3:  return 'BUY'
    if score <= -3: return 'SELL'
    return 'HOLD'


def get_signal_detail(bars: pd.DataFrame) -> dict:
    if len(bars) < 26:
        return {'signal': 'HOLD', 'score': 0, 'details': {}}

    regime = detect_market_regime(bars)
    cs     = candlestick_score(bars)
    mom    = candle_momentum_score(bars)
    m      = macd_signal(bars)
    v      = vwap_signal(bars)
    b      = bollinger_signal(bars)
    e      = ema_trend(bars)
    r_val  = 50
    try:
        r_val = round(rsi(bars['close']), 1)
    except:
        pass

    patterns = []
    if three_candle_bull(bars):     patterns.append('3-Candle Bull Run ▲▲▲')
    if three_candle_bear(bars):     patterns.append('3-Candle Bear Run ▼▼▼')
    if is_bullish_engulfing(bars):  patterns.append('Bullish Engulfing')
    if is_bearish_engulfing(bars):  patterns.append('Bearish Engulfing')
    if is_hammer(bars):             patterns.append('Hammer')
    if is_shooting_star(bars):      patterns.append('Shooting Star')
    if is_morning_star(bars):       patterns.append('Morning Star')
    if is_evening_star(bars):       patterns.append('Evening Star')
    if is_doji(bars):               patterns.append('Doji')

    score = mom*2 + cs*2
    if m=='BUY': score+=2
    elif m=='SELL': score-=2
    if v=='BUY': score+=1
    elif v=='SELL': score-=1
    if b=='BUY': score+=1
    elif b=='SELL': score-=1
    if e=='BUY': score+=1
    elif e=='SELL': score-=1
    if r_val < 40: score+=1
    elif r_val > 60: score-=1

    signal = 'BUY' if score >= 3 else 'SELL' if score <= -3 else 'HOLD'

    return {
        'signal':   signal,
        'score':    score,
        'regime':   regime,
        'rsi':      r_val,
        'macd':     m,
        'vwap':     v,
        'bollinger':b,
        'ema':      e,
        'patterns': patterns if patterns else ['None'],
    }


# ─── SLC Strategy (preserved) ─────────────────────────────────────────────────

def stochastic(bars: pd.DataFrame, k_period=14, d_period=3):
    low_min  = bars['low'].rolling(k_period).min()
    high_max = bars['high'].rolling(k_period).max()
    k = 100 * (bars['close'] - low_min) / (high_max - low_min).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def htf_structure(bars_htf: pd.DataFrame) -> str:
    if len(bars_htf) < 10:
        return 'neutral'
    highs = bars_htf['high'].values
    lows  = bars_htf['low'].values
    hh = highs[-1] > highs[-5] > highs[-10]
    hl = lows[-1]  > lows[-5]  > lows[-10]
    lh = highs[-1] < highs[-5] < highs[-10]
    ll = lows[-1]  < lows[-5]  < lows[-10]
    if hh and hl: return 'bullish'
    if lh and ll: return 'bearish'
    return 'neutral'


def find_supply_demand_zones(bars: pd.DataFrame, lookback=50) -> dict:
    if len(bars) < lookback:
        lookback = len(bars)
    recent   = bars.tail(lookback).copy()
    recent['body']  = abs(recent['close'] - recent['open'])
    recent['range'] = recent['high'] - recent['low']
    avg_body = recent['body'].mean()
    supply_zones, demand_zones = [], []
    for i in range(2, len(recent) - 1):
        row  = recent.iloc[i]
        body = row['body']
        if row['close'] < row['open'] and body > avg_body * 1.5:
            supply_zones.append({'top': row['high'], 'bottom': row['open'], 'index': i})
        if row['close'] > row['open'] and body > avg_body * 1.5:
            demand_zones.append({'top': row['close'], 'bottom': row['low'], 'index': i})
    return {
        'supply': supply_zones[-3:] if supply_zones else [],
        'demand': demand_zones[-3:] if demand_zones else [],
    }


def stoch_confirmation(bars: pd.DataFrame, side: str) -> bool:
    if len(bars) < 20: return False
    k, d = stochastic(bars)
    k_now, k_prev = k.iloc[-1], k.iloc[-2]
    d_now, d_prev = d.iloc[-1], d.iloc[-2]
    if side == 'BUY':
        return bool(k.iloc[-4:-1].min() < 25 and k_prev <= d_prev and k_now > d_now)
    if side == 'SELL':
        return bool(k.iloc[-4:-1].max() > 75 and k_prev >= d_prev and k_now < d_now)
    return False


def price_at_zone(price: float, zones: list, tolerance: float = 0.003) -> bool:
    for z in zones:
        zone_mid = (z['top'] + z['bottom']) / 2
        if abs(price - zone_mid) / zone_mid <= tolerance:
            return True
        if z['bottom'] <= price <= z['top']:
            return True
    return False


def slc_signal(bars_5m: pd.DataFrame, bars_htf: pd.DataFrame) -> str:
    if bars_5m.empty or len(bars_5m) < 20:
        return 'HOLD'
    structure = htf_structure(bars_htf if not bars_htf.empty else bars_5m)
    if structure == 'neutral':
        return 'HOLD'
    price = float(bars_5m['close'].iloc[-1])
    zones = find_supply_demand_zones(bars_5m)
    if structure == 'bullish' and price_at_zone(price, zones['demand']):
        if stoch_confirmation(bars_5m, 'BUY'):
            return 'BUY'
    if structure == 'bearish' and price_at_zone(price, zones['supply']):
        if stoch_confirmation(bars_5m, 'SELL'):
            return 'SELL'
    return 'HOLD'
