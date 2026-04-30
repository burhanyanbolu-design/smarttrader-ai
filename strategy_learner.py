"""
Strategy Learner — 24/7 Strategy Discovery + Auto Backtester + Self-Learning Engine
====================================================================================
Primary: GPT-4o generates strategies from its knowledge base
Secondary: Reddit r/Daytrading, r/algotrading etc
Third: NewsAPI filtered to trading sites
Fallback: Web search

Run modes:
  python strategy_learner.py --mode auto   # 24/7 server mode
  python strategy_learner.py --mode once   # run one cycle and exit
  python strategy_learner.py               # interactive menu
"""

import os, sys, json, time, logging, hashlib, requests, threading, argparse, random
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

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

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
NEWS_API_KEY    = os.getenv("NEWS_API_KEY", "")
SCAN_INTERVAL   = int(os.getenv("SCAN_INTERVAL_MINUTES", "15"))

STRATEGIES_FILE = "data/discovered_strategies.json"
SCORES_FILE     = "data/strategy_scores.json"
BEST_FILE       = "data/best_strategies.json"
SEEN_FILE       = "data/seen_sources.json"

STRATEGY_KEYWORDS = [
    "strategy", "indicator", "signal", "entry", "exit",
    "RSI", "MACD", "EMA", "backtest", "setup", "pattern",
    "profitable", "win rate", "system", "method", "scalp",
    "swing", "breakout", "reversal", "momentum"
]

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

# ── Source 1: GPT-4o generates strategies from knowledge base ─────────────────
# Most reliable — GPT knows thousands of real strategies from YouTube, Reddit etc

GPT_STRATEGY_PROMPTS = [
    "Describe a profitable RSI divergence day trading strategy for US stocks with specific entry rules, exit rules, stop loss and take profit levels",
    "Describe a MACD crossover with EMA 200 trend filter trading strategy with specific entry exit rules and risk management",
    "Describe a VWAP mean reversion day trading strategy for stocks with specific entry exit rules",
    "Describe an opening range breakout (ORB) trading strategy for stocks with specific rules",
    "Describe a 3-candle momentum trading strategy with RSI confirmation for day trading",
    "Describe a Bollinger Band squeeze breakout strategy with volume confirmation",
    "Describe an EMA 9/21 crossover strategy with MACD confirmation for day trading stocks",
    "Describe a gap and go trading strategy for stocks with specific entry exit rules",
    "Describe a support resistance breakout strategy with volume confirmation for stocks",
    "Describe a moving average ribbon trading strategy for trend following stocks",
    "Describe a price action pin bar reversal strategy for day trading stocks",
    "Describe a volume profile VPOC trading strategy for stocks",
    "Describe a stochastic oscillator oversold bounce strategy for stocks",
    "Describe a double bottom reversal trading strategy with RSI confirmation",
    "Describe a bull flag breakout continuation strategy for momentum stocks",
    "Describe a VWAP anchored deviation trading strategy for stocks",
    "Describe a supertrend indicator trading strategy for stocks",
    "Describe a Keltner channel breakout trading strategy",
    "Describe an ATR trailing stop momentum strategy for stocks",
    "Describe a 5-minute opening range breakout strategy with volume filter",
]

def generate_from_gpt() -> list:
    """Ask GPT-4o to describe known trading strategies — most reliable source"""
    if not OPENAI_API_KEY:
        log.warning("No OPENAI_API_KEY — skipping GPT generation")
        return []

    results = []
    selected = random.sample(GPT_STRATEGY_PROMPTS, min(5, len(GPT_STRATEGY_PROMPTS)))

    for prompt in selected:
        sid = _hash(prompt)
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an expert day trader with 20 years experience. Describe trading strategies with very specific, concrete, codeable rules. Include exact indicator values, entry conditions, exit conditions, stop loss and take profit."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=600,
                temperature=0.2,
            )
            content = response.choices[0].message.content
            results.append({
                "source":  "gpt-knowledge",
                "title":   prompt[:100],
                "content": content,
                "score":   80,
                "url":     "",
                "id":      sid,
            })
            log.info(f"GPT generated strategy: {prompt[:60]}...")
            time.sleep(1)
        except Exception as e:
            log.warning(f"GPT strategy gen error: {e}")

    log.info(f"GPT-generated: {len(results)} strategies")
    return results

# ── Source 2: Reddit ──────────────────────────────────────────────────────────

SUBREDDITS = [
    "Daytrading", "algotrading", "stocks", "StockMarket",
    "wallstreetbets", "options", "technicalanalysis", "Trading",
    "Forex", "SwingTrading"
]

def scrape_reddit() -> list:
    posts = []
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0",
        "Accept": "application/json",
    }
    for sub in SUBREDDITS[:5]:  # limit to 5 to avoid rate limits
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=20"
            r   = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                log.warning(f"Reddit {sub}: status {r.status_code}")
                time.sleep(3)
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
                    "content": body[:3000] if body else title,
                    "score":   score,
                    "url":     f"https://reddit.com{p.get('permalink', '')}",
                    "id":      _hash(title + body[:50]),
                })
            time.sleep(2)
        except Exception as e:
            log.warning(f"Reddit {sub} error: {e}")
    log.info(f"Reddit: {len(posts)} posts found")
    return posts

# ── Source 3: NewsAPI filtered to trading sites ───────────────────────────────

def scrape_news() -> list:
    if not NEWS_API_KEY:
        return []
    articles = []
    terms = [
        "day trading strategy RSI MACD stocks",
        "EMA crossover trading strategy backtest",
        "VWAP trading strategy stocks tutorial",
    ]
    for term in terms:
        try:
            r = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": term, "language": "en", "sortBy": "relevancy",
                    "pageSize": 5, "apiKey": NEWS_API_KEY,
                    "domains": "investopedia.com,babypips.com,thebalancemoney.com,benzinga.com,stockanalysis.com"
                },
                timeout=15,
            )
            for a in r.json().get("articles", []):
                title   = a.get("title", "")
                content = a.get("description", "") or ""
                if not title or "[Removed]" in title:
                    continue
                if not any(k.lower() in (title+content).lower() for k in STRATEGY_KEYWORDS):
                    continue
                articles.append({
                    "source":  a.get("source", {}).get("name", "news"),
                    "title":   title,
                    "content": content[:2000],
                    "score":   60,
                    "url":     a.get("url", ""),
                    "id":      _hash(title),
                })
            time.sleep(1)
        except Exception as e:
            log.warning(f"News error: {e}")
    log.info(f"News: {len(articles)} articles found")
    return articles

# ── GPT-4o Strategy Extractor ─────────────────────────────────────────────────

EXTRACT_PROMPT = """You are an expert quantitative trader.
Analyse this trading content and extract any concrete trading strategy rules.

Return a JSON object:
{
  "has_strategy": true/false,
  "strategy_name": "descriptive name",
  "indicators": ["RSI", "MACD", etc],
  "entry_rules": ["specific entry conditions"],
  "exit_rules": ["specific exit conditions"],
  "timeframe": "1min/5min/15min/1hour/daily",
  "asset_type": "stocks/forex/crypto/any",
  "stop_loss": "description or %",
  "take_profit": "description or %",
  "summary": "one sentence",
  "implementable": true/false,
  "confidence": 1-10
}
Only set implementable=true if rules are specific enough to code."""

CODE_PROMPT = """You are an expert Python quant developer.
Convert these trading strategy rules into a Python function.
Requirements:
1. Accept pandas DataFrame: columns open, high, low, close, volume
2. Return 'BUY', 'SELL', or 'HOLD'
3. Use only pandas and numpy (imported as pd, np)
4. Handle edge cases (not enough data → return 'HOLD')
5. Name: strategy_{snake_case_name}
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
            max_tokens=600, temperature=0.1,
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
            max_tokens=800, temperature=0.1,
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
                ticker = yf.Ticker(symbol)
                df = ticker.history(period="90d", interval="1d")
                if df is None or df.empty or len(df) < 30:
                    continue
                df.columns = [c.lower() for c in df.columns]
                available = [c for c in ["open","high","low","close","volume"] if c in df.columns]
                df = df[available].copy()
                if "close" not in df.columns:
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
                        "symbol": symbol, "trades": len(trades),
                        "win_rate": wins / len(trades) * 100,
                        "profit_factor": pf,
                        "total_pnl": sum(t["pnl"] for t in trades),
                    })
                time.sleep(0.5)
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
        log.info(f"✅ Saved: '{strategy.get('strategy_name')}' score={s} WR={bt.get('win_rate')}% PF={bt.get('profit_factor')}")

    def best(self, n=10, min_score=40):
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
        content.extend(generate_from_gpt())   # PRIMARY — always works
        content.extend(scrape_reddit())        # SECONDARY
        content.extend(scrape_news())          # THIRD
        new = [c for c in content if not self.memory.seen_before(c["id"])]
        log.info(f"Total new items: {len(new)} / {len(content)}")
        return new

    def process(self, item):
        self.memory.mark_seen(item["id"])
        log.info(f"Extracting: {item['title'][:70]}...")

        strategy = extract_strategy(item)
        if not strategy.get("has_strategy") or not strategy.get("implementable"):
            log.info("No implementable strategy found")
            return

        log.info(f"Strategy: {strategy.get('strategy_name')} (conf={strategy.get('confidence')})")

        code = generate_code(strategy)
        if not code:
            log.warning("Could not generate code")
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
            time.sleep(2)

        self.memory.export_best()
        log.info(f"\nSTATS: {self.memory.stats()}")

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
        log.info("Starting in AUTO (server) mode")
        learner.run_forever()

    elif args.mode == "once":
        log.info("Running one cycle...")
        learner.running = True
        learner.run_cycle()
        log.info("Done.")

    else:
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
        elif choice == "3":
            for i, s in enumerate(learner.memory.best(), 1):
                st, bt = s["strategy"], s["backtest"]
                print(f"\n{i}. {st.get('strategy_name')} | Score:{s['score']} WR:{bt.get('win_rate')}% PF:{bt.get('profit_factor')}")
        elif choice == "4":
            for k, v in learner.memory.stats().items():
                print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
