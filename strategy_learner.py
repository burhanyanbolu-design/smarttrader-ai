"""
Strategy Learner — 24/7 Web Scraper + Auto Backtester + Self-Learning Engine
============================================================================
Scrapes YouTube, Reddit, financial blogs for trading strategies.
Extracts rules using GPT-4o, backtests them, scores them, and learns over time.
The best strategies are saved and fed into the live trader automatically.

Run modes:
  python strategy_learner.py            # interactive menu
  python strategy_learner.py --mode auto  # 24/7 server mode (no input needed)
  python strategy_learner.py --mode once  # run one cycle and exit
"""

import os
import sys
import json
import time
import logging
import hashlib
import requests
import threading
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/learner.log"),
    ]
)
log = logging.getLogger("strategy_learner")

# ── Config from environment ───────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
NEWS_API_KEY   = os.getenv("NEWS_API_KEY", "")
SCAN_INTERVAL  = int(os.getenv("SCAN_INTERVAL_MINUTES", "30"))

STRATEGIES_FILE = "data/discovered_strategies.json"
SCORES_FILE     = "data/strategy_scores.json"
BEST_FILE       = "data/best_strategies.json"
SEEN_FILE       = "data/seen_sources.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default

def _save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

def _hash(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]

# ── Source 1: Reddit ──────────────────────────────────────────────────────────

SUBREDDITS = [
    "Daytrading", "stocks", "StockMarket", "algotrading",
    "investing", "wallstreetbets", "Forex", "options",
    "technicalanalysis", "Trading"
]

STRATEGY_KEYWORDS = [
    "strategy", "indicator", "signal", "entry", "exit",
    "RSI", "MACD", "EMA", "backtest", "setup", "pattern",
    "profitable", "win rate", "system", "method"
]

def scrape_reddit() -> list:
    posts   = []
    headers = {"User-Agent": "SmartTrader-AI/1.0"}
    for sub in SUBREDDITS:
        for sort in ["hot", "top"]:
            try:
                url = f"https://www.reddit.com/r/{sub}/{sort}.json?limit=25&t=week"
                r   = requests.get(url, headers=headers, timeout=10)
                if r.status_code != 200:
                    continue
                for post in r.json().get("data", {}).get("children", []):
                    p     = post.get("data", {})
                    title = p.get("title", "")
                    body  = p.get("selftext", "")
                    score = p.get("score", 0)
                    text  = (title + " " + body).lower()
                    if not any(k.lower() in text for k in STRATEGY_KEYWORDS):
                        continue
                    if score < 10:
                        continue
                    posts.append({
                        "source":  f"reddit/r/{sub}",
                        "title":   title,
                        "content": body[:2000],
                        "score":   score,
                        "url":     f"https://reddit.com{p.get('permalink', '')}",
                        "id":      _hash(title + body[:100]),
                    })
                time.sleep(1)
            except Exception as e:
                log.warning(f"Reddit {sub} error: {e}")
    log.info(f"Reddit: {len(posts)} strategy posts found")
    return posts

# ── Source 2: Financial News ──────────────────────────────────────────────────

SEARCH_TERMS = [
    "day trading strategy 2025",
    "best stock trading strategy backtest",
    "RSI MACD EMA trading strategy",
    "momentum breakout trading strategy",
    "VWAP opening range breakout strategy",
]

def scrape_news() -> list:
    if not NEWS_API_KEY:
        log.warning("NEWS_API_KEY not set — skipping news scrape")
        return []
    articles = []
    for term in SEARCH_TERMS:
        try:
            r = requests.get(
                "https://newsapi.org/v2/everything",
                params={"q": term, "language": "en", "sortBy": "relevancy",
                        "pageSize": 10, "apiKey": NEWS_API_KEY},
                timeout=10,
            )
            for a in r.json().get("articles", []):
                title   = a.get("title", "")
                content = a.get("description", "") or a.get("content", "")
                if not title or "[Removed]" in title:
                    continue
                articles.append({
                    "source":  a.get("source", {}).get("name", "news"),
                    "title":   title,
                    "content": content[:2000],
                    "score":   50,
                    "url":     a.get("url", ""),
                    "id":      _hash(title),
                })
            time.sleep(0.5)
        except Exception as e:
            log.warning(f"News scrape error: {e}")
    log.info(f"News: {len(articles)} articles found")
    return articles

# ── Source 3: DuckDuckGo web search ──────────────────────────────────────────

WEB_QUERIES = [
    "best day trading strategy 2025 stocks",
    "RSI MACD crossover strategy tutorial",
    "EMA 9 21 trading strategy",
    "VWAP trading strategy explained",
    "momentum trading strategy stocks tutorial",
]

def scrape_web() -> list:
    results = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for query in WEB_QUERIES:
        try:
            r = requests.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1},
                headers=headers,
                timeout=10,
            )
            data = r.json()
            for item in data.get("RelatedTopics", [])[:5]:
                text = item.get("Text", "")
                url  = item.get("FirstURL", "")
                if text and len(text) > 50:
                    results.append({
                        "source":  "web",
                        "title":   text[:200],
                        "content": text[:1000],
                        "score":   30,
                        "url":     url,
                        "id":      _hash(text[:100]),
                    })
            time.sleep(1)
        except Exception as e:
            log.warning(f"Web search error: {e}")
    log.info(f"Web: {len(results)} results found")
    return results

# ── GPT-4o Strategy Extractor ─────────────────────────────────────────────────

EXTRACT_PROMPT = """You are an expert quantitative trader.
Analyse this trading content and extract any concrete trading strategy rules.

Return a JSON object with this exact structure:
{
  "has_strategy": true/false,
  "strategy_name": "descriptive name",
  "indicators": ["list of indicators used e.g. RSI, MACD, EMA"],
  "entry_rules": ["list of specific entry conditions"],
  "exit_rules": ["list of specific exit conditions"],
  "timeframe": "1min/5min/15min/1hour/daily",
  "asset_type": "stocks/forex/crypto/any",
  "stop_loss": "description or percentage",
  "take_profit": "description or percentage",
  "claimed_win_rate": "if mentioned, else null",
  "summary": "one sentence summary",
  "implementable": true/false,
  "confidence": 1-10
}

Only set implementable to true if the rules are specific enough to code.
If no concrete strategy is described, set has_strategy to false."""

CODE_PROMPT = """You are an expert Python quant developer.
Convert these trading strategy rules into a Python function.

Requirements:
1. Accept a pandas DataFrame: columns open, high, low, close, volume
2. Return 'BUY', 'SELL', or 'HOLD'
3. Use only pandas and numpy (imported as pd, np)
4. Handle edge cases (not enough data → return 'HOLD')
5. Name the function: strategy_{snake_case_name}

Return ONLY the Python function, no explanation, no imports."""

def extract_strategy(content: dict) -> dict:
    if not OPENAI_API_KEY:
        return {"has_strategy": False}
    try:
        client   = OpenAI(api_key=OPENAI_API_KEY)
        text     = f"Title: {content['title']}\n\nContent: {content['content']}"
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user",   "content": text},
            ],
            max_tokens=600,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        result["source_id"]  = content["id"]
        result["source_url"] = content.get("url", "")
        result["source"]     = content.get("source", "")
        result["scraped_at"] = datetime.now().isoformat()
        return result
    except Exception as e:
        log.warning(f"GPT extract error: {e}")
        return {"has_strategy": False}

def generate_code(strategy: dict) -> str:
    if not OPENAI_API_KEY or not strategy.get("implementable"):
        return ""
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        rules  = json.dumps({
            "name":        strategy.get("strategy_name", "unknown"),
            "indicators":  strategy.get("indicators", []),
            "entry_rules": strategy.get("entry_rules", []),
            "exit_rules":  strategy.get("exit_rules", []),
            "timeframe":   strategy.get("timeframe", "5min"),
            "stop_loss":   strategy.get("stop_loss", "1.5%"),
            "take_profit": strategy.get("take_profit", "3%"),
        }, indent=2)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": CODE_PROMPT},
                {"role": "user",   "content": rules},
            ],
            max_tokens=800,
            temperature=0.1,
        )
        code = response.choices[0].message.content.strip()
        if code.startswith("```"):
            code = "\n".join(code.split("\n")[1:-1])
        return code
    except Exception as e:
        log.warning(f"GPT code gen error: {e}")
        return ""

# ── Backtester ────────────────────────────────────────────────────────────────

def backtest(code: str) -> dict:
    try:
        import yfinance as yf
        import numpy as np

        symbols   = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
        namespace = {"pd": __import__("pandas"), "np": np}

        try:
            exec(code, namespace)
        except Exception as e:
            return {"error": f"Code error: {e}", "win_rate": 0, "profit_factor": 0}

        func = next((v for k, v in namespace.items()
                     if k.startswith("strategy_") and callable(v)), None)
        if not func:
            return {"error": "No function found", "win_rate": 0, "profit_factor": 0}

        all_results = []
        for symbol in symbols:
            try:
                df = yf.download(symbol, period="90d", interval="1d",
                                 progress=False, auto_adjust=True)
                if df.empty or len(df) < 30:
                    continue
                df.columns = [c.lower() for c in df.columns]
                df = df[["open", "high", "low", "close", "volume"]].copy()

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
            except Exception as e:
                log.warning(f"Backtest {symbol}: {e}")

        if not all_results:
            return {"error": "No results", "win_rate": 0, "profit_factor": 0}

        return {
            "win_rate":      round(sum(r["win_rate"] for r in all_results) / len(all_results), 1),
            "profit_factor": round(sum(r["profit_factor"] for r in all_results) / len(all_results), 2),
            "total_trades":  sum(r["trades"] for r in all_results),
            "per_symbol":    all_results,
            "error":         None,
        }
    except Exception as e:
        return {"error": str(e), "win_rate": 0, "profit_factor": 0}

# ── Scoring ───────────────────────────────────────────────────────────────────

def score(strategy: dict, bt: dict) -> float:
    s = 0.0
    wr = bt.get("win_rate", 0)
    if wr >= 65:    s += 40
    elif wr >= 55:  s += 30
    elif wr >= 50:  s += 20
    elif wr >= 45:  s += 10

    pf = bt.get("profit_factor", 0)
    if pf >= 2.0:   s += 30
    elif pf >= 1.5: s += 22
    elif pf >= 1.2: s += 15
    elif pf >= 1.0: s += 8

    trades = bt.get("total_trades", 0)
    if trades >= 50:   s += 20
    elif trades >= 30: s += 15
    elif trades >= 15: s += 10
    elif trades >= 5:  s += 5

    s += strategy.get("confidence", 5)
    return round(s, 1)

# ── Memory ────────────────────────────────────────────────────────────────────

class Memory:
    def __init__(self):
        self.strategies = _load(STRATEGIES_FILE, {})
        self.scores     = _load(SCORES_FILE, {})
        self.seen       = set(_load(SEEN_FILE, []))

    def save(self):
        _save(STRATEGIES_FILE, self.strategies)
        _save(SCORES_FILE, self.scores)
        _save(SEEN_FILE, list(self.seen))

    def seen_before(self, sid): return sid in self.seen
    def mark_seen(self, sid):   self.seen.add(sid)

    def add(self, strategy, code, bt):
        sid = strategy.get("source_id", _hash(str(strategy)))
        s   = score(strategy, bt)
        self.strategies[sid] = {
            "strategy": strategy, "code": code,
            "backtest": bt, "score": s,
            "added_at": datetime.now().isoformat(),
        }
        self.scores[sid] = s
        self.save()
        log.info(f"Saved: '{strategy.get('strategy_name')}' score={s}")

    def best(self, n=10, min_score=45):
        ranked = sorted(
            [(sid, d) for sid, d in self.strategies.items()
             if self.scores.get(sid, 0) >= min_score],
            key=lambda x: self.scores.get(x[0], 0), reverse=True
        )
        return [d for _, d in ranked[:n]]

    def export_best(self):
        best = self.best()
        _save(BEST_FILE, {
            "updated_at": datetime.now().isoformat(),
            "count":      len(best),
            "strategies": best,
        })
        log.info(f"Exported {len(best)} best strategies → {BEST_FILE}")

    def stats(self):
        total = len(self.strategies)
        return {
            "total_discovered":  total,
            "high_quality_60+":  sum(1 for s in self.scores.values() if s >= 60),
            "avg_score":         round(sum(self.scores.values()) / max(total, 1), 1),
            "best_score":        max(self.scores.values()) if self.scores else 0,
            "sources_seen":      len(self.seen),
        }

# ── Main Learner ──────────────────────────────────────────────────────────────

class StrategyLearner:
    def __init__(self):
        self.memory  = Memory()
        self.running = False
        self.cycle   = 0

    def scrape_all(self):
        content = []
        content.extend(scrape_reddit())
        content.extend(scrape_news())
        content.extend(scrape_web())
        new = [c for c in content if not self.memory.seen_before(c["id"])]
        log.info(f"Total new items: {len(new)} / {len(content)}")
        return new

    def process(self, item):
        self.memory.mark_seen(item["id"])
        log.info(f"Extracting: {item['title'][:70]}...")

        strategy = extract_strategy(item)
        if not strategy.get("has_strategy") or not strategy.get("implementable"):
            return

        log.info(f"Strategy found: {strategy.get('strategy_name')} (conf={strategy.get('confidence')})")

        code = generate_code(strategy)
        if not code:
            return

        log.info("Backtesting...")
        bt = backtest(code)
        if bt.get("error"):
            log.warning(f"Backtest failed: {bt['error']}")
            return

        log.info(f"Result: WR={bt['win_rate']}% PF={bt['profit_factor']} Trades={bt['total_trades']}")
        self.memory.add(strategy, code, bt)

    def run_cycle(self):
        self.cycle += 1
        log.info(f"\n{'='*60}")
        log.info(f"CYCLE #{self.cycle} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log.info(f"{'='*60}")

        items = self.scrape_all()
        for i, item in enumerate(items):
            if not self.running:
                break
            log.info(f"[{i+1}/{len(items)}] {item['source']}")
            self.process(item)
            time.sleep(2)  # GPT rate limit

        self.memory.export_best()

        stats = self.memory.stats()
        log.info(f"\nSTATS: {stats}")

    def run_forever(self):
        self.running = True
        log.info(f"Strategy Learner started — scanning every {SCAN_INTERVAL} min")
        while self.running:
            try:
                self.run_cycle()
            except Exception as e:
                log.error(f"Cycle error: {e}")
            log.info(f"Sleeping {SCAN_INTERVAL} minutes...")
            for _ in range(SCAN_INTERVAL * 60):
                if not self.running:
                    break
                time.sleep(1)

    def stop(self):
        self.running = False


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["auto", "once", "menu"], default="menu")
    args = parser.parse_args()

    learner = StrategyLearner()

    if args.mode == "auto":
        # Server mode — runs forever, no input needed
        log.info("Starting in AUTO (server) mode")
        learner.run_forever()

    elif args.mode == "once":
        log.info("Running one cycle...")
        learner.running = True
        learner.run_cycle()
        log.info("Done.")

    else:
        # Interactive menu
        print("\n" + "="*60)
        print("  STRATEGY LEARNER")
        print("="*60)
        print("1. Run one cycle now")
        print("2. Start 24/7 continuous learning")
        print("3. Show best strategies")
        print("4. Show stats")

        choice = input("\nChoice (1-4): ").strip()

        if choice == "1":
            learner.running = True
            learner.run_cycle()

        elif choice == "2":
            try:
                learner.run_forever()
            except KeyboardInterrupt:
                learner.stop()
                print("\nStopped.")

        elif choice == "3":
            best = learner.memory.best()
            if not best:
                print("No strategies yet. Run a cycle first.")
            else:
                for i, s in enumerate(best, 1):
                    st = s["strategy"]
                    bt = s["backtest"]
                    print(f"\n{i}. {st.get('strategy_name')}")
                    print(f"   Score: {s['score']} | WR: {bt.get('win_rate')}% | PF: {bt.get('profit_factor')}")
                    print(f"   Indicators: {', '.join(st.get('indicators', []))}")

        elif choice == "4":
            for k, v in learner.memory.stats().items():
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
