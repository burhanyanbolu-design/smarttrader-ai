"""
Research Intelligence Engine
=============================
Collects from academic journals, institutional whitepapers, fintech blogs
and quant forums. Extracts PATTERNS and LOGIC — not signals.

Sources:
- SSRN (academic quant papers)
- JSTOR (academic research)
- McKinsey, Deloitte, BCG (institutional frameworks)
- Finextra, The Financial Brand (fintech blogs)
- Niche quant forums

Extraction approach:
- NOT "find strategies" — extracts repeatable entry conditions
- NOT opinions — extracts data-backed logic
- Translates math/frameworks into IF/EXIT/RISK rules

Run modes:
  python research_intelligence.py --mode auto   # 24/7 server mode
  python research_intelligence.py --mode once   # one cycle
  python research_intelligence.py               # interactive menu
"""

import os, sys, json, time, logging, hashlib, requests, argparse, random
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

os.makedirs("data/research", exist_ok=True)
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/research.log"),
    ]
)
log = logging.getLogger("research_intelligence")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
NEWS_API_KEY   = os.getenv("NEWS_API_KEY", "")
SCAN_INTERVAL  = int(os.getenv("RESEARCH_INTERVAL_MINUTES", "60"))

RESEARCH_FILE  = "data/research/extracted_patterns.json"
RULES_FILE     = "data/research/trading_rules.json"
BEST_FILE      = "data/best_strategies.json"
SEEN_FILE      = "data/research/seen_research.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default

def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

def _hash(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]

# ── Source 1: SSRN Academic Papers ───────────────────────────────────────────

SSRN_TOPICS = [
    "momentum trading strategy stocks",
    "mean reversion equity markets",
    "quantitative trading signals",
    "market microstructure order flow",
    "volatility clustering trading",
    "statistical arbitrage stocks",
    "behavioral finance overreaction",
    "high frequency trading patterns",
    "factor investing momentum value",
    "risk management position sizing",
]

def scrape_ssrn() -> list:
    """Search SSRN for quantitative trading papers"""
    results = []
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

    for topic in SSRN_TOPICS[:5]:
        try:
            # SSRN search via their public search
            r = requests.get(
                "https://papers.ssrn.com/sol3/results.cfm",
                params={"txtkey": topic, "subjectmatterid": ""},
                headers=headers,
                timeout=15,
            )
            if r.status_code == 200 and len(r.text) > 500:
                # Extract paper titles from HTML
                from html.parser import HTMLParser

                class TitleParser(HTMLParser):
                    def __init__(self):
                        super().__init__()
                        self.titles = []
                        self.in_title = False
                        self.current = ""

                    def handle_starttag(self, tag, attrs):
                        attrs_dict = dict(attrs)
                        if tag == "a" and "class" in attrs_dict:
                            if "title" in attrs_dict.get("class", "").lower():
                                self.in_title = True

                    def handle_endtag(self, tag):
                        if tag == "a" and self.in_title:
                            if self.current.strip():
                                self.titles.append(self.current.strip())
                            self.in_title = False
                            self.current = ""

                    def handle_data(self, data):
                        if self.in_title:
                            self.current += data

                parser = TitleParser()
                parser.feed(r.text)

                for title in parser.titles[:3]:
                    if len(title) > 20:
                        results.append({
                            "source":  "ssrn",
                            "title":   title,
                            "content": f"Academic paper on: {topic}. Title: {title}",
                            "topic":   topic,
                            "url":     "https://papers.ssrn.com",
                            "id":      _hash(title),
                        })
            time.sleep(2)
        except Exception as e:
            log.warning(f"SSRN error for '{topic}': {e}")

    log.info(f"SSRN: {len(results)} papers found")
    return results

# ── Source 2: NewsAPI — Institutional & Academic ──────────────────────────────

RESEARCH_QUERIES = [
    "quantitative trading strategy research 2025",
    "momentum factor investing academic research",
    "market microstructure liquidity trading",
    "algorithmic trading risk management framework",
    "behavioral finance trading patterns research",
    "hedge fund strategy quantitative research",
    "mean reversion trading academic study",
    "volatility trading strategy research",
]

def scrape_research_news() -> list:
    if not NEWS_API_KEY:
        return []
    results = []
    for query in RESEARCH_QUERIES[:4]:
        try:
            r = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "language": "en",
                    "sortBy": "relevancy",
                    "pageSize": 5,
                    "apiKey": NEWS_API_KEY,
                    "domains": "finextra.com,thefinancialbrand.com,risk.net,ft.com,bloomberg.com,wsj.com,quantpedia.com,alphaarchitect.com,portfoliovisualizer.com"
                },
                timeout=15,
            )
            for a in r.json().get("articles", []):
                title   = a.get("title", "")
                content = a.get("description", "") or a.get("content", "")
                if not title or "[Removed]" in title:
                    continue
                results.append({
                    "source":  a.get("source", {}).get("name", "research"),
                    "title":   title,
                    "content": content[:3000],
                    "topic":   query,
                    "url":     a.get("url", ""),
                    "id":      _hash(title),
                })
            time.sleep(1)
        except Exception as e:
            log.warning(f"Research news error: {e}")
    log.info(f"Research news: {len(results)} articles found")
    return results

# ── Source 3: GPT-4o as Research Synthesizer ──────────────────────────────────
# GPT has read McKinsey, Deloitte, BCG, SSRN, JSTOR papers in training

RESEARCH_SYNTHESIS_PROMPTS = [
    # Market Microstructure
    "Based on market microstructure research, what are the most reliable order flow patterns that predict short-term price movement in stocks? Give specific, measurable conditions.",
    "What does academic research say about bid-ask spread behavior as a trading signal? Give specific entry conditions based on spread patterns.",
    "Based on liquidity zone research, how do institutional traders identify support/resistance? Give specific rules.",

    # Quantitative Signals
    "Based on academic momentum factor research (Jegadeesh & Titman, AQR), what are the specific rules for a momentum trading strategy? Give exact lookback periods and entry conditions.",
    "What does mean reversion research say about optimal entry conditions? Give specific statistical thresholds (z-score, standard deviations) for entry and exit.",
    "Based on volatility clustering research (GARCH models), what trading rules can be derived? Give specific conditions.",

    # Behavioral Finance
    "Based on behavioral finance research on overreaction and underreaction, what are specific trading rules that exploit these patterns in stocks?",
    "What does research on retail trader psychology (fear/greed cycles) tell us about optimal entry timing? Give specific measurable conditions.",
    "Based on sentiment analysis research, what velocity of sentiment change predicts price movement? Give specific thresholds.",

    # Risk Management (McKinsey/Deloitte frameworks)
    "Based on institutional risk management frameworks from McKinsey and Deloitte, what are the optimal position sizing rules for day trading? Give specific formulas.",
    "What does professional risk management research say about stop-loss placement? Give specific rules based on ATR or volatility.",
    "Based on drawdown control research, what are the specific rules for daily loss limits and position reduction?",

    # Institutional Behavior
    "Based on hedge fund research and 13F filings analysis, what patterns in institutional positioning predict stock price movement? Give specific rules.",
    "What does research on central bank policy impact show about trading around Fed announcements? Give specific entry/exit rules.",
    "Based on research on dark pool activity and block trades, what signals indicate institutional accumulation?",

    # Alternative Data
    "Based on academic research on news sentiment and stock returns, what specific sentiment scores or velocity metrics predict price movement?",
    "What does research on social media sentiment (Reddit, Twitter) show about predictive signals? Give specific measurable thresholds.",
    "Based on volume anomaly research, what specific volume patterns reliably predict breakouts?",
]

def synthesize_from_research() -> list:
    """Use GPT-4o to synthesize institutional and academic research into trading rules"""
    if not OPENAI_API_KEY:
        return []

    results = []
    selected = random.sample(RESEARCH_SYNTHESIS_PROMPTS, min(4, len(RESEARCH_SYNTHESIS_PROMPTS)))

    RESEARCH_SYSTEM_PROMPT = """You are a quantitative research analyst who has read thousands of 
academic papers from SSRN, JSTOR, and whitepapers from McKinsey, Deloitte, BCG, and AQR.

Your job is to extract SPECIFIC, MEASURABLE, CODEABLE trading rules from research.

Rules must be:
- Based on data and research, not opinions
- Specific enough to code (exact numbers, thresholds, conditions)
- Include entry conditions, exit conditions, stop loss, take profit
- Reference the research basis

Do NOT give vague advice. Give exact IF/THEN rules."""

    for prompt in selected:
        sid = _hash(prompt)
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=700,
                temperature=0.1,
            )
            content = response.choices[0].message.content
            results.append({
                "source":  "institutional-research",
                "title":   prompt[:100],
                "content": content,
                "topic":   prompt,
                "url":     "",
                "id":      sid,
            })
            log.info(f"Research synthesized: {prompt[:60]}...")
            time.sleep(1)
        except Exception as e:
            log.warning(f"Research synthesis error: {e}")

    log.info(f"Research synthesis: {len(results)} insights generated")
    return results

# ── Pattern Extractor ─────────────────────────────────────────────────────────

PATTERN_EXTRACT_PROMPT = """You are a quantitative trading rule extractor.

Analyse this research content and extract SPECIFIC TRADING RULES.

Focus on:
1. Entry conditions (exact IF statements)
2. Exit conditions (exact WHEN to exit)
3. Risk controls (stop loss, position size)
4. Market conditions (when this works/doesn't work)

Return JSON:
{
  "has_rules": true/false,
  "rule_name": "descriptive name",
  "research_basis": "what research/theory this comes from",
  "market_condition": "trending/ranging/volatile/any",
  "entry_conditions": [
    "specific measurable condition 1",
    "specific measurable condition 2"
  ],
  "exit_conditions": [
    "specific exit rule 1"
  ],
  "stop_loss": "specific rule e.g. 1.5x ATR below entry",
  "take_profit": "specific rule e.g. 2x ATR above entry",
  "position_size": "specific rule e.g. 1% risk per trade",
  "indicators_needed": ["RSI", "ATR", etc],
  "timeframe": "1min/5min/15min/1hour/daily",
  "confidence": 1-10,
  "implementable": true/false,
  "notes": "any important caveats"
}"""

CODE_FROM_RESEARCH_PROMPT = """You are an expert Python quant developer.

Convert these research-based trading rules into a Python function.

The function must:
1. Accept pandas DataFrame: columns open, high, low, close, volume
2. Return 'BUY', 'SELL', or 'HOLD'
3. Use only pandas and numpy (imported as pd, np)
4. Implement the exact conditions specified
5. Handle edge cases gracefully
6. Name: strategy_{snake_case_name}

Return ONLY the Python function, no explanation, no imports."""

def extract_patterns(content: dict) -> dict:
    """Extract specific trading patterns from research content"""
    if not OPENAI_API_KEY:
        return {"has_rules": False}
    try:
        client   = OpenAI(api_key=OPENAI_API_KEY)
        text     = f"Research Topic: {content['title']}\n\nContent:\n{content['content']}"
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": PATTERN_EXTRACT_PROMPT},
                {"role": "user",   "content": text},
            ],
            max_tokens=700,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        result["source_id"]    = content["id"]
        result["source"]       = content.get("source", "")
        result["source_url"]   = content.get("url", "")
        result["extracted_at"] = datetime.now().isoformat()
        return result
    except Exception as e:
        log.warning(f"Pattern extract error: {e}")
        return {"has_rules": False}

def generate_code_from_rules(rules: dict) -> str:
    """Convert research rules into Python trading function"""
    if not OPENAI_API_KEY or not rules.get("implementable"):
        return ""
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        rule_text = json.dumps({
            "name":              rules.get("rule_name", "unknown"),
            "research_basis":    rules.get("research_basis", ""),
            "entry_conditions":  rules.get("entry_conditions", []),
            "exit_conditions":   rules.get("exit_conditions", []),
            "stop_loss":         rules.get("stop_loss", "1.5% below entry"),
            "take_profit":       rules.get("take_profit", "3% above entry"),
            "indicators_needed": rules.get("indicators_needed", []),
            "timeframe":         rules.get("timeframe", "daily"),
        }, indent=2)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": CODE_FROM_RESEARCH_PROMPT},
                {"role": "user",   "content": rule_text},
            ],
            max_tokens=900,
            temperature=0.1,
        )
        code = response.choices[0].message.content.strip()
        if code.startswith("```"):
            code = "\n".join(code.split("\n")[1:-1])
        return code
    except Exception as e:
        log.warning(f"Code gen error: {e}")
        return ""

# ── Backtester ────────────────────────────────────────────────────────────────

def backtest_rule(code: str) -> dict:
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
                        if signal == "SELL" or pnl <= -1.5 or pnl >= 3.0:
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

def score_rule(rules: dict, bt: dict) -> float:
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

    # Bonus for research-backed rules
    s += rules.get("confidence", 5)
    if rules.get("research_basis"):
        s += 5  # bonus for having research backing

    return round(s, 1)

# ── Memory ────────────────────────────────────────────────────────────────────

class ResearchMemory:
    def __init__(self):
        self.patterns = _load(RESEARCH_FILE, {})
        self.rules    = _load(RULES_FILE, {})
        self.seen     = set(_load(SEEN_FILE, []))

    def save(self):
        _save(RESEARCH_FILE, self.patterns)
        _save(RULES_FILE, self.rules)
        _save(SEEN_FILE, list(self.seen))

    def seen_before(self, sid): return sid in self.seen
    def mark_seen(self, sid):   self.seen.add(sid)

    def add_rule(self, rules, code, bt):
        sid   = rules.get("source_id", _hash(str(rules)))
        s     = score_rule(rules, bt)
        entry = {
            "rules":    rules,
            "code":     code,
            "backtest": bt,
            "score":    s,
            "added_at": datetime.now().isoformat(),
        }
        self.rules[sid] = entry
        self.save()

        # Also export to shared best_strategies.json so trader can use it
        self._merge_to_best(entry)
        log.info(f"✅ Research rule saved: '{rules.get('rule_name')}' score={s} WR={bt.get('win_rate')}% PF={bt.get('profit_factor')} basis='{rules.get('research_basis','')[:50]}'")

    def _merge_to_best(self, entry):
        """Merge high-scoring research rules into the shared best_strategies.json"""
        if entry["score"] < 40:
            return
        best_data = _load(BEST_FILE, {"strategies": []})
        strategies = best_data.get("strategies", [])

        # Convert research rule format to strategy format
        strategy_entry = {
            "strategy": {
                "strategy_name": entry["rules"].get("rule_name", "Research Rule"),
                "indicators":    entry["rules"].get("indicators_needed", []),
                "source":        f"research/{entry['rules'].get('source', '')}",
                "research_basis":entry["rules"].get("research_basis", ""),
                "timeframe":     entry["rules"].get("timeframe", "daily"),
                "confidence":    entry["rules"].get("confidence", 7),
            },
            "code":     entry["code"],
            "backtest": entry["backtest"],
            "score":    entry["score"],
            "added_at": entry["added_at"],
        }
        strategies.append(strategy_entry)
        strategies = sorted(strategies, key=lambda x: x.get("score", 0), reverse=True)[:20]
        _save(BEST_FILE, {
            "updated_at": datetime.now().isoformat(),
            "count":      len(strategies),
            "strategies": strategies,
        })

    def best_rules(self, n=10):
        return sorted(self.rules.values(), key=lambda x: x.get("score", 0), reverse=True)[:n]

    def stats(self):
        total = len(self.rules)
        scores = [r.get("score", 0) for r in self.rules.values()]
        return {
            "total_rules":      total,
            "high_quality_60+": sum(1 for s in scores if s >= 60),
            "avg_score":        round(sum(scores) / max(total, 1), 1),
            "best_score":       max(scores) if scores else 0,
            "sources_seen":     len(self.seen),
        }

# ── Main Research Engine ──────────────────────────────────────────────────────

class ResearchIntelligence:
    def __init__(self):
        self.memory  = ResearchMemory()
        self.running = False
        self.cycle   = 0

    def collect_all(self):
        content = []
        content.extend(synthesize_from_research())  # PRIMARY — institutional knowledge
        content.extend(scrape_research_news())       # SECONDARY — fintech blogs
        content.extend(scrape_ssrn())                # THIRD — academic papers
        new = [c for c in content if not self.memory.seen_before(c["id"])]
        log.info(f"New research items: {len(new)} / {len(content)}")
        return new

    def process(self, item):
        self.memory.mark_seen(item["id"])
        log.info(f"Analysing: {item['title'][:70]}...")

        # Extract patterns and rules
        rules = extract_patterns(item)
        if not rules.get("has_rules") or not rules.get("implementable"):
            log.info("No implementable rules found in this research")
            return

        log.info(f"Rules extracted: '{rules.get('rule_name')}' basis='{rules.get('research_basis','')[:50]}'")

        # Generate code
        code = generate_code_from_rules(rules)
        if not code:
            log.warning("Could not generate code from rules")
            return

        # Backtest
        log.info("Backtesting research-based rule...")
        bt = backtest_rule(code)
        if bt.get("error"):
            log.warning(f"Backtest failed: {bt['error']}")
            return

        log.info(f"Backtest: WR={bt['win_rate']}% PF={bt['profit_factor']} Trades={bt['total_trades']}")
        self.memory.add_rule(rules, code, bt)

    def run_cycle(self):
        self.cycle += 1
        log.info(f"\n{'='*60}")
        log.info(f"RESEARCH CYCLE #{self.cycle} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log.info(f"{'='*60}")

        items = self.collect_all()
        for i, item in enumerate(items):
            if not self.running:
                break
            log.info(f"[{i+1}/{len(items)}] {item['source']}")
            self.process(item)
            time.sleep(2)

        stats = self.memory.stats()
        log.info(f"\nRESEARCH STATS: {stats}")

    def run_forever(self):
        self.running = True
        log.info(f"Research Intelligence started — scanning every {SCAN_INTERVAL} min")
        while self.running:
            try:
                self.run_cycle()
            except Exception as e:
                log.error(f"Research cycle error: {e}")
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

    engine = ResearchIntelligence()

    if args.mode == "auto":
        log.info("Research Intelligence starting in AUTO mode")
        engine.run_forever()

    elif args.mode == "once":
        log.info("Running one research cycle...")
        engine.running = True
        engine.run_cycle()
        log.info("Done.")

    else:
        print("\n" + "="*60)
        print("  RESEARCH INTELLIGENCE ENGINE")
        print("  Sources: SSRN, McKinsey, Deloitte, Finextra")
        print("="*60)
        print("1. Run one research cycle")
        print("2. Start 24/7 continuous research")
        print("3. Show best rules found")
        print("4. Show stats")
        choice = input("\nChoice (1-4): ").strip()

        if choice == "1":
            engine.running = True
            engine.run_cycle()
        elif choice == "2":
            try:
                engine.run_forever()
            except KeyboardInterrupt:
                engine.stop()
        elif choice == "3":
            rules = engine.memory.best_rules()
            if not rules:
                print("No rules yet. Run a cycle first.")
            else:
                for i, r in enumerate(rules, 1):
                    ru = r["rules"]
                    bt = r["backtest"]
                    print(f"\n{i}. {ru.get('rule_name')}")
                    print(f"   Score: {r['score']} | WR: {bt.get('win_rate')}% | PF: {bt.get('profit_factor')}")
                    print(f"   Basis: {ru.get('research_basis','')[:80]}")
                    print(f"   Entry: {ru.get('entry_conditions',['?'])[0][:80]}")
        elif choice == "4":
            for k, v in engine.memory.stats().items():
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

