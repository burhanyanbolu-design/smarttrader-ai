"""
Shared Backtester — uses Alpaca API for historical data
Replaces yfinance which is blocked on the server
"""

import os, time, logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("backtester")

API_KEY    = os.getenv("ALPACA_API_KEY", "")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
PAPER      = "paper" in BASE_URL

SYMBOLS = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]


def get_historical_bars(symbol: str, days: int = 90) -> pd.DataFrame:
    """Fetch historical daily bars from Alpaca"""
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
        import pytz

        client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
        now    = datetime.now(pytz.UTC)
        start  = now - timedelta(days=days + 10)

        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame(1, TimeFrameUnit.Day),
            start=start,
            end=now,
            feed="iex",
        )
        bars = client.get_stock_bars(req).df
        if bars.empty:
            return pd.DataFrame()
        if isinstance(bars.index, pd.MultiIndex):
            bars = bars.droplevel(0)
        bars.index.name = "timestamp"
        cols = [c for c in ["open","high","low","close","volume"] if c in bars.columns]
        return bars[cols].copy()
    except Exception as e:
        log.warning(f"Alpaca bars failed for {symbol}: {e}")
        return pd.DataFrame()


def run_backtest(code: str) -> dict:
    """
    Backtest a strategy function against Alpaca historical data.
    code: Python code string containing a strategy_xxx function
    """
    namespace = {"pd": pd, "np": np}

    try:
        exec(code, namespace)
    except Exception as e:
        return {"error": f"Code error: {e}", "win_rate": 0, "profit_factor": 0}

    func = next((v for k, v in namespace.items()
                 if k.startswith("strategy_") and callable(v)), None)
    if not func:
        return {"error": "No strategy function found", "win_rate": 0, "profit_factor": 0}

    all_results = []
    for symbol in SYMBOLS:
        try:
            df = get_historical_bars(symbol, days=90)
            if df.empty or len(df) < 30:
                log.warning(f"No data for {symbol}")
                continue

            trades, position = [], None
            for i in range(30, len(df)):
                window = df.iloc[:i+1]
                try:
                    signal = func(window)
                except Exception:
                    signal = "HOLD"
                price = float(df["close"].iloc[i])

                if signal == "BUY" and position is None:
                    position = price
                elif position is not None:
                    pnl = (price - position) / position * 100
                    if signal == "SELL" or pnl <= -1.5 or pnl >= 2.5:
                        trades.append({"pnl": pnl, "win": pnl > 0})
                        position = None

            if trades:
                wins     = sum(1 for t in trades if t["win"])
                losses   = len(trades) - wins
                avg_win  = sum(t["pnl"] for t in trades if t["win"]) / max(wins, 1)
                avg_loss = abs(sum(t["pnl"] for t in trades if not t["win"]) / max(losses, 1))
                pf       = (avg_win * wins) / (avg_loss * losses) if losses > 0 and avg_loss > 0 else 0
                all_results.append({
                    "symbol":        symbol,
                    "trades":        len(trades),
                    "win_rate":      wins / len(trades) * 100,
                    "profit_factor": pf,
                    "total_pnl":     sum(t["pnl"] for t in trades),
                })
            time.sleep(0.3)
        except Exception as e:
            log.warning(f"Backtest {symbol}: {e}")

    if not all_results:
        return {"error": "No backtest results", "win_rate": 0, "profit_factor": 0}

    return {
        "win_rate":      round(sum(r["win_rate"] for r in all_results) / len(all_results), 1),
        "profit_factor": round(sum(r["profit_factor"] for r in all_results) / len(all_results), 2),
        "total_trades":  sum(r["trades"] for r in all_results),
        "per_symbol":    all_results,
        "error":         None,
    }

