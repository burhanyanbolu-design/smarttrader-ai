"""
Strategy Scanner — Bot 1
Continuously scans and scores all strategies against current market conditions.
Finds the best performing strategy for each symbol and market regime.
Saves results to strategy_scores.json for the trader to consume.
"""
import os, json, time, logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger('strategy_scanner')

SCORES_FILE  = 'strategy_scores.json'
RESULTS_FILE = 'scan_results.json'

# All strategy combinations to test
STRATEGY_CONFIGS = [
    {'name': 'momentum_strong',  'rsi_buy': 40, 'rsi_sell': 60, 'score_threshold': 6,  'weight_momentum': 3, 'weight_macd': 3, 'weight_bb': 1, 'weight_rsi': 1},
    {'name': 'mean_reversion',   'rsi_buy': 35, 'rsi_sell': 65, 'score_threshold': 5,  'weight_momentum': 1, 'weight_macd': 1, 'weight_bb': 3, 'weight_rsi': 3},
    {'name': 'trend_following',  'rsi_buy': 45, 'rsi_sell': 55, 'score_threshold': 7,  'weight_momentum': 2, 'weight_macd': 3, 'weight_bb': 1, 'weight_rsi': 2},
    {'name': 'conservative',     'rsi_buy': 30, 'rsi_sell': 70, 'score_threshold': 8,  'weight_momentum': 2, 'weight_macd': 2, 'weight_bb': 2, 'weight_rsi': 2},
    {'name': 'aggressive',       'rsi_buy': 45, 'rsi_sell': 55, 'score_threshold': 4,  'weight_momentum': 3, 'weight_macd': 2, 'weight_bb': 1, 'weight_rsi': 1},
    {'name': 'slc_focused',      'rsi_buy': 40, 'rsi_sell': 60, 'score_threshold': 5,  'weight_momentum': 2, 'weight_macd': 2, 'weight_bb': 2, 'weight_rsi': 2},
    {'name': 'vwap_momentum',    'rsi_buy': 42, 'rsi_sell': 58, 'score_threshold': 5,  'weight_momentum': 2, 'weight_macd': 2, 'weight_bb': 1, 'weight_rsi': 2},
    {'name': 'breakout',         'rsi_buy': 50, 'rsi_sell': 50, 'score_threshold': 7,  'weight_momentum': 4, 'weight_macd': 2, 'weight_bb': 2, 'weight_rsi': 1},
]

SYMBOLS = [
    'AAPL','MSFT','NVDA','TSLA','META','GOOGL','AMZN','AMD',
    'SPY','QQQ','IWM','ARKK','SMH',
    'JPM','BAC','GS','XOM','CVX','UNH','LLY',
    'PLTR','CRWD','COIN','MSTR','SHOP','NET','PANW',
    'V','MA','LMT','RTX','GLD','GDX','DAL','UAL',
]


def get_data_client():
    from alpaca.data.historical import StockHistoricalDataClient
    return StockHistoricalDataClient(
        os.getenv('ALPACA_API_KEY'),
        os.getenv('ALPACA_SECRET_KEY')
    )


def fetch_bars(symbol: str, days: int = 30) -> pd.DataFrame:
    """Fetch historical bars for scanning"""
    try:
        import yfinance as yf
        end   = datetime.now()
        start = end - timedelta(days=days)
        df = yf.download(symbol, start=start, end=end,
                         interval='1d', progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.columns = [c.lower() for c in df.columns]
        return df[['open', 'high', 'low', 'close', 'volume']].dropna()
    except Exception as e:
        log.warning(f"Fetch failed {symbol}: {e}")
        return pd.DataFrame()


def score_strategy_on_bars(bars: pd.DataFrame, config: dict) -> dict:
    """Score a strategy config against historical bars"""
    from strategies import (ema, rsi, macd_signal, bollinger_signal,
                             ema_trend, candle_momentum_score, candlestick_score,
                             vwap_signal, detect_market_regime)

    if len(bars) < 30:
        return {'win_rate': 0, 'trades': 0, 'pnl_pct': 0, 'score': 0}

    trades = []
    in_trade = False
    entry_price = 0

    for i in range(26, len(bars)):
        window = bars.iloc[:i+1]
        score  = 0

        mom = candle_momentum_score(window)
        score += mom * config['weight_momentum']

        cs = candlestick_score(window)
        score += cs * 1

        m = macd_signal(window)
        if m == 'BUY':  score += config['weight_macd']
        if m == 'SELL': score -= config['weight_macd']

        b = bollinger_signal(window)
        if b == 'BUY':  score += config['weight_bb']
        if b == 'SELL': score -= config['weight_bb']

        try:
            r = rsi(window['close'])
            if r < config['rsi_buy']:   score += config['weight_rsi']
            elif r > config['rsi_sell']: score -= config['weight_rsi']
        except:
            pass

        threshold = config['score_threshold']
        signal = 'BUY' if score >= threshold else 'SELL' if score <= -threshold else 'HOLD'

        price = float(bars.iloc[i]['close'])

        if not in_trade and signal == 'BUY':
            in_trade    = True
            entry_price = price

        elif in_trade and signal == 'SELL':
            pnl_pct = (price - entry_price) / entry_price * 100
            trades.append({'pnl_pct': pnl_pct, 'win': pnl_pct > 0})
            in_trade = False

    if not trades:
        return {'win_rate': 0, 'trades': 0, 'pnl_pct': 0, 'score': 0}

    win_rate = sum(1 for t in trades if t['win']) / len(trades) * 100
    avg_pnl  = sum(t['pnl_pct'] for t in trades) / len(trades)
    score    = win_rate * 0.6 + avg_pnl * 0.4

    return {
        'win_rate':  round(win_rate, 1),
        'trades':    len(trades),
        'pnl_pct':   round(avg_pnl, 2),
        'score':     round(score, 2),
    }


def scan_symbol(symbol: str) -> dict:
    """Scan all strategies for a single symbol"""
    bars = fetch_bars(symbol, days=60)
    if bars.empty or len(bars) < 30:
        return None

    from strategies import detect_market_regime
    try:
        regime = detect_market_regime(bars)
    except:
        regime = 'unknown'

    results = {}
    best_score  = -999
    best_config = None

    for config in STRATEGY_CONFIGS:
        result = score_strategy_on_bars(bars, config)
        results[config['name']] = result
        if result['score'] > best_score and result['trades'] >= 3:
            best_score  = result['score']
            best_config = config['name']

    return {
        'symbol':      symbol,
        'regime':      regime,
        'best_strategy': best_config or 'momentum_strong',
        'best_score':  round(best_score, 2),
        'strategies':  results,
        'scanned_at':  datetime.now().strftime('%H:%M:%S'),
    }


def run_scan(symbols=None) -> dict:
    """Run full strategy scan across all symbols"""
    if symbols is None:
        symbols = SYMBOLS

    log.info(f"Starting strategy scan for {len(symbols)} symbols...")
    print(f"\n{'='*55}")
    print(f"  STRATEGY SCANNER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Scanning {len(symbols)} symbols × {len(STRATEGY_CONFIGS)} strategies")
    print(f"{'='*55}")

    all_results = {}
    strategy_votes = {c['name']: 0 for c in STRATEGY_CONFIGS}

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(scan_symbol, sym): sym for sym in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                result = future.result()
                if result:
                    all_results[sym] = result
                    best = result.get('best_strategy')
                    if best:
                        strategy_votes[best] = strategy_votes.get(best, 0) + 1
                    print(f"  {sym:6} | regime={result['regime']:14} | best={result['best_strategy']:20} | score={result['best_score']:.1f}")
            except Exception as e:
                log.warning(f"Scan failed {sym}: {e}")

    # Overall best strategy
    overall_best = max(strategy_votes, key=strategy_votes.get) if strategy_votes else 'momentum_strong'

    # Regime distribution
    regimes = [r['regime'] for r in all_results.values()]
    regime_counts = {r: regimes.count(r) for r in set(regimes)}
    dominant_regime = max(regime_counts, key=regime_counts.get) if regime_counts else 'unknown'

    summary = {
        'scanned_at':      datetime.now().isoformat(),
        'symbols_scanned': len(all_results),
        'overall_best_strategy': overall_best,
        'strategy_votes':  strategy_votes,
        'dominant_regime': dominant_regime,
        'regime_counts':   regime_counts,
        'symbol_results':  all_results,
    }

    # Save results
    with open(SCORES_FILE, 'w') as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\n  Overall best strategy : {overall_best}")
    print(f"  Dominant market regime: {dominant_regime}")
    print(f"  Results saved to {SCORES_FILE}")
    print(f"{'='*55}\n")

    return summary


def get_best_strategy_for(symbol: str) -> str:
    """Get the best strategy for a specific symbol from last scan"""
    try:
        with open(SCORES_FILE) as f:
            data = json.load(f)
        result = data.get('symbol_results', {}).get(symbol)
        if result:
            return result.get('best_strategy', 'momentum_strong')
        return data.get('overall_best_strategy', 'momentum_strong')
    except:
        return 'momentum_strong'


def get_overall_best_strategy() -> str:
    """Get the overall best strategy from last scan"""
    try:
        with open(SCORES_FILE) as f:
            data = json.load(f)
        return data.get('overall_best_strategy', 'momentum_strong')
    except:
        return 'momentum_strong'


def get_dominant_regime() -> str:
    """Get the dominant market regime from last scan"""
    try:
        with open(SCORES_FILE) as f:
            data = json.load(f)
        return data.get('dominant_regime', 'unknown')
    except:
        return 'unknown'


def run_scanner_loop(interval_minutes: int = 30):
    """Run scanner continuously every N minutes"""
    log.info(f"Strategy scanner started — scanning every {interval_minutes} minutes")
    while True:
        try:
            run_scan()
        except Exception as e:
            log.error(f"Scanner error: {e}")
        time.sleep(interval_minutes * 60)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    run_scan()
