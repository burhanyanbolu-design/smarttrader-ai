"""
Strategy Bridge
===============
Connects the Strategy Learner to the Live Trader.
Reads best_strategies.json and runs learned strategy functions
alongside the existing signals.

The trader calls get_learned_signal(bars) which:
1. Loads the top scored strategies from best_strategies.json
2. Runs each strategy function against current bars
3. Returns a combined vote (BUY/SELL/HOLD) + confidence score
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime

log = logging.getLogger("strategy_bridge")

BEST_FILE = "/opt/smarttrader/data/best_strategies.json"
FALLBACK  = "data/best_strategies.json"

_cached_strategies = []
_cache_time        = None
CACHE_SECONDS      = 300  # reload every 5 minutes


def _load_best_strategies(min_score=60, top_n=5) -> list:
    """Load top scored strategies from the learner output"""
    global _cached_strategies, _cache_time

    now = datetime.now()
    if _cache_time and (now - _cache_time).seconds < CACHE_SECONDS:
        return _cached_strategies

    path = BEST_FILE if os.path.exists(BEST_FILE) else FALLBACK
    try:
        with open(path) as f:
            data = json.load(f)
        strategies = data.get("strategies", [])
        # Filter by min score and sort
        good = [s for s in strategies if s.get("score", 0) >= min_score]
        good = sorted(good, key=lambda x: x.get("score", 0), reverse=True)[:top_n]
        _cached_strategies = good
        _cache_time = now
        if good:
            log.info(f"Bridge: loaded {len(good)} learned strategies (best score: {good[0].get('score')})")
        return good
    except Exception as e:
        log.warning(f"Bridge: could not load strategies: {e}")
        return []


def _compile_strategy(code: str):
    """Compile a strategy function from code string"""
    try:
        namespace = {"pd": pd, "np": np}
        exec(code, namespace)
        func = next((v for k, v in namespace.items()
                     if k.startswith("strategy_") and callable(v)), None)
        return func
    except Exception as e:
        log.warning(f"Bridge: compile error: {e}")
        return None


def get_learned_signal(bars: pd.DataFrame) -> dict:
    """
    Run all learned strategies against current bars.
    Returns combined signal with confidence.
    """
    if bars is None or len(bars) < 30:
        return {"signal": "HOLD", "score": 0, "votes": 0, "source": "learned"}

    strategies = _load_best_strategies(min_score=40, top_n=10)
    if not strategies:
        return {"signal": "HOLD", "score": 0, "votes": 0, "source": "learned"}

    buy_votes  = 0
    sell_votes = 0
    total_score = 0
    names = []

    for s in strategies:
        code  = s.get("code", "")
        score = s.get("score", 0)
        name  = s.get("strategy", {}).get("strategy_name", "unknown")

        if not code:
            continue

        func = _compile_strategy(code)
        if not func:
            continue

        try:
            signal = func(bars)
            if signal == "BUY":
                buy_votes  += 1
                total_score += score
                names.append(f"{name}(BUY)")
            elif signal == "SELL":
                sell_votes  += 1
                total_score -= score
                names.append(f"{name}(SELL)")
        except Exception as e:
            log.warning(f"Bridge: strategy '{name}' error: {e}")

    total_votes = buy_votes + sell_votes
    if total_votes == 0:
        return {"signal": "HOLD", "score": 0, "votes": 0, "source": "learned"}

    # Majority vote
    if buy_votes > sell_votes and buy_votes >= 2:
        signal = "BUY"
    elif sell_votes > buy_votes and sell_votes >= 2:
        signal = "SELL"
    elif buy_votes == 1 and sell_votes == 0:
        signal = "BUY"
    elif sell_votes == 1 and buy_votes == 0:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "signal":     signal,
        "score":      round(abs(total_score) / max(total_votes, 1), 1),
        "votes":      total_votes,
        "buy_votes":  buy_votes,
        "sell_votes": sell_votes,
        "strategies": names,
        "source":     "learned",
    }


def get_combined_signal(bars: pd.DataFrame, existing_score: int) -> dict:
    """
    Combine existing trader signal with learned strategies.
    existing_score: score from the current trader's combined_signal()

    Returns enhanced signal with learned strategy boost.
    """
    learned = get_learned_signal(bars)

    # Boost existing score with learned signal
    boost = 0
    if learned["signal"] == "BUY"  and learned["votes"] >= 2:
        boost = +3
    elif learned["signal"] == "BUY" and learned["votes"] == 1:
        boost = +1
    elif learned["signal"] == "SELL" and learned["votes"] >= 2:
        boost = -3
    elif learned["signal"] == "SELL" and learned["votes"] == 1:
        boost = -1

    enhanced_score = existing_score + boost

    return {
        "original_score":  existing_score,
        "learned_signal":  learned["signal"],
        "learned_votes":   learned["votes"],
        "boost":           boost,
        "enhanced_score":  enhanced_score,
        "strategies_used": learned.get("strategies", []),
    }

