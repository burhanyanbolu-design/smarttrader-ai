"""
SmartTrader-AI Web Dashboard
Live view of strategy learner + Alpaca trading account
Access via: http://YOUR_SERVER_IP:5000
"""

import os
import json
from datetime import datetime
from flask import Flask, render_template_string
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── Alpaca account data ───────────────────────────────────────────────────────

def get_alpaca_data():
    try:
        from alpaca.trading.client import TradingClient
        api_key    = os.getenv("ALPACA_API_KEY", "")
        secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        base_url   = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        paper      = "paper" in base_url

        if not api_key or not secret_key:
            return None

        client  = TradingClient(api_key, secret_key, paper=paper)
        account = client.get_account()

        equity      = float(account.equity)
        last_equity = float(account.last_equity)
        cash        = float(account.cash)
        pnl         = equity - last_equity
        pnl_pct     = (pnl / last_equity * 100) if last_equity else 0
        buying_pw   = float(account.buying_power)

        # Open positions
        positions = []
        for p in client.get_all_positions():
            positions.append({
                "symbol":  p.symbol,
                "qty":     p.qty,
                "entry":   round(float(p.avg_entry_price), 2),
                "current": round(float(p.current_price), 2),
                "pl":      round(float(p.unrealized_pl), 2),
                "pl_pct":  round(float(p.unrealized_plpc) * 100, 2),
            })

        # Recent orders from trade log
        trades = []
        try:
            with open("trade_log.jsonl") as f:
                lines = f.readlines()
            for line in lines[-20:][::-1]:
                trades.append(json.loads(line.strip()))
        except Exception:
            pass

        # Win/loss stats from trade log
        all_trades = []
        try:
            with open("trade_log.jsonl") as f:
                for line in f:
                    t = json.loads(line.strip())
                    if t.get("pnl") is not None:
                        all_trades.append(t)
        except Exception:
            pass

        wins   = sum(1 for t in all_trades if t.get("pnl", 0) > 0)
        losses = sum(1 for t in all_trades if t.get("pnl", 0) < 0)
        total_pnl = sum(t.get("pnl", 0) for t in all_trades)

        return {
            "equity":      round(equity, 2),
            "cash":        round(cash, 2),
            "pnl":         round(pnl, 2),
            "pnl_pct":     round(pnl_pct, 2),
            "buying_pw":   round(buying_pw, 2),
            "positions":   positions,
            "trades":      trades[:10],
            "wins":        wins,
            "losses":      losses,
            "total_pnl":   round(total_pnl, 2),
            "mode":        "PAPER" if paper else "LIVE",
        }
    except Exception as e:
        return {"error": str(e)}

BEST_FILE       = "data/best_strategies.json"
STRATEGIES_FILE = "data/discovered_strategies.json"
SCORES_FILE     = "data/strategy_scores.json"
LOG_FILE        = "logs/learner.log"

def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default

def get_last_logs(n=50):
    try:
        with open(LOG_FILE) as f:
            lines = f.readlines()
        return [l.strip() for l in lines[-n:]][::-1]
    except Exception:
        return ["No logs yet..."]

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>SmartTrader-AI Dashboard</title>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="30">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    * { margin:0; padding:0; box-sizing:border-box; }
    body { background:#0d0d0d; color:#e8e8e8; font-family:'Courier New',monospace; }
    .header { background:#111; padding:20px 30px; border-bottom:2px solid #00ff88; display:flex; justify-content:space-between; align-items:center; }
    .header h1 { color:#00ff88; font-size:22px; }
    .header .time { color:#666; font-size:12px; }
    .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; padding:20px 30px; }
    .card { background:#161616; border:1px solid #222; border-radius:8px; padding:20px; }
    .card .label { color:#666; font-size:11px; margin-bottom:8px; }
    .card .value { font-size:28px; font-weight:bold; color:#00ff88; }
    .card .value.red { color:#ff4455; }
    .card .value.yellow { color:#ffaa00; }
    .card .value.blue { color:#00ccff; }
    .section { padding:0 30px 20px; }
    .section h2 { color:#00ff88; font-size:14px; margin-bottom:12px; padding-bottom:6px; border-bottom:1px solid #222; }
    .strategy { background:#161616; border:1px solid #222; border-radius:6px; padding:16px; margin-bottom:10px; }
    .strategy .name { color:#00ccff; font-size:14px; font-weight:bold; margin-bottom:8px; }
    .strategy .meta { display:flex; gap:20px; flex-wrap:wrap; }
    .strategy .badge { background:#222; padding:4px 10px; border-radius:4px; font-size:11px; }
    .strategy .badge.green { color:#00ff88; }
    .strategy .badge.yellow { color:#ffaa00; }
    .strategy .badge.red { color:#ff4455; }
    .strategy .badge.blue { color:#00ccff; }
    .strategy .indicators { color:#666; font-size:11px; margin-top:8px; }
    .strategy .source { color:#444; font-size:10px; margin-top:6px; }
    .logs { background:#0a0a0a; border:1px solid #222; border-radius:6px; padding:16px; height:300px; overflow-y:auto; }
    .log-line { font-size:11px; padding:2px 0; border-bottom:1px solid #111; }
    .log-line.warn { color:#ffaa00; }
    .log-line.error { color:#ff4455; }
    .log-line.info { color:#00ccff; }
    .log-line.success { color:#00ff88; }
    .empty { color:#444; text-align:center; padding:40px; }
    .status-dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:#00ff88; margin-right:8px; animation:pulse 2s infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
    .refresh { color:#444; font-size:11px; text-align:center; padding:10px; }
  </style>
</head>
<body>

<div class="header">
  <h1>🎯 SmartTrader-AI <span style="color:#666;font-size:14px;">Strategy Learner</span></h1>
  <div>
    <span class="status-dot"></span>
    <span style="color:#00ff88;font-size:12px;">RUNNING</span>
    <span class="time" style="margin-left:20px;">{{ now }}</span>
  </div>
</div>

<!-- Stats Cards -->
<div class="grid">
  <div class="card">
    <div class="label">STRATEGIES DISCOVERED</div>
    <div class="value">{{ stats.total }}</div>
  </div>
  <div class="card">
    <div class="label">HIGH QUALITY (60+)</div>
    <div class="value blue">{{ stats.high_quality }}</div>
  </div>
  <div class="card">
    <div class="label">BEST SCORE</div>
    <div class="value {% if stats.best_score >= 70 %}green{% elif stats.best_score >= 50 %}yellow{% else %}red{% endif %}">
      {{ stats.best_score }}
    </div>
  </div>
  <div class="card">
    <div class="label">AVG SCORE</div>
    <div class="value yellow">{{ stats.avg_score }}</div>
  </div>
</div>

<!-- Best Strategies -->
<div class="section">
  <h2>🏆 BEST STRATEGIES FOUND</h2>
  {% if best %}
    {% for s in best %}
    <div class="strategy">
      <div class="name">{{ loop.index }}. {{ s.strategy.strategy_name or 'Unknown Strategy' }}</div>
      <div class="meta">
        <span class="badge {% if s.score >= 70 %}green{% elif s.score >= 50 %}yellow{% else %}red{% endif %}">
          Score: {{ s.score }}
        </span>
        <span class="badge {% if s.backtest.win_rate >= 60 %}green{% elif s.backtest.win_rate >= 50 %}yellow{% else %}red{% endif %}">
          Win Rate: {{ s.backtest.win_rate }}%
        </span>
        <span class="badge {% if s.backtest.profit_factor >= 1.5 %}green{% elif s.backtest.profit_factor >= 1.0 %}yellow{% else %}red{% endif %}">
          Profit Factor: {{ s.backtest.profit_factor }}
        </span>
        <span class="badge blue">Trades: {{ s.backtest.total_trades }}</span>
        <span class="badge">{{ s.strategy.timeframe or '?' }}</span>
      </div>
      <div class="indicators">
        Indicators: {{ s.strategy.indicators | join(', ') if s.strategy.indicators else 'N/A' }}
      </div>
      <div class="source">Source: {{ s.strategy.source or 'unknown' }} | Added: {{ s.added_at[:16] if s.added_at else '?' }}</div>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty">No strategies discovered yet — bot is still learning...</div>
  {% endif %}
</div>

<!-- Live Logs -->
<div class="section">
  <h2>📋 LIVE LOGS</h2>
  <div class="logs">
    {% for line in logs %}
      <div class="log-line
        {% if 'ERROR' in line or 'error' in line %}error
        {% elif 'WARNING' in line or 'warn' in line %}warn
        {% elif 'Saved' in line or 'Exported' in line or 'SUCCESS' in line %}success
        {% else %}info{% endif %}">
        {{ line }}
      </div>
    {% endfor %}
  </div>
</div>

<div class="refresh">Auto-refreshes every 30 seconds</div>

</body>
</html>
"""

@app.route("/status")
def status_report():
    """Full status report page"""
    import subprocess

    def run(cmd):
        try:
            return subprocess.check_output(cmd, shell=True, text=True, timeout=10).strip()
        except Exception:
            return "N/A"

    # Learner stats
    best_data  = _load(BEST_FILE, {"strategies": [], "updated_at": "never"})
    all_strats = _load(STRATEGIES_FILE, {})
    all_scores = _load(SCORES_FILE, {})
    total      = len(all_strats)
    high       = sum(1 for s in all_scores.values() if s >= 60)
    best_score = max(all_scores.values()) if all_scores else 0

    # Trade log
    trades, pnl, wins, losses = [], 0, 0, 0
    try:
        with open("/opt/stocktrader/trade_log.jsonl") as f:
            for line in f:
                try:
                    t = json.loads(line.strip())
                    if t.get("pnl") is not None:
                        trades.append(t)
                        pnl += t["pnl"]
                        if t["pnl"] > 0: wins += 1
                        else: losses += 1
                except Exception:
                    pass
    except Exception:
        pass

    # Service status
    learner_status = run("systemctl is-active smarttrader")
    trader_status  = run("systemctl is-active stocktrader 2>/dev/null || echo unknown")
    dashboard_status = run("systemctl is-active dashboard")

    logs = get_last_logs(30)
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    STATUS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>SmartTrader-AI — Status Report</title>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="30">
  <style>
    * { margin:0; padding:0; box-sizing:border-box; }
    body { background:#0d0d0d; color:#e8e8e8; font-family:'Courier New',monospace; padding:20px; }
    h1 { color:#00ff88; margin-bottom:20px; }
    h2 { color:#00ccff; margin:20px 0 10px; font-size:14px; letter-spacing:1px; }
    .grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-bottom:20px; }
    .card { background:#161616; border:1px solid #222; border-radius:8px; padding:16px; }
    .label { color:#666; font-size:11px; margin-bottom:6px; }
    .value { font-size:24px; font-weight:bold; }
    .green { color:#00ff88; } .red { color:#ff4455; } .yellow { color:#ffaa00; } .blue { color:#00ccff; }
    .service { display:flex; align-items:center; gap:10px; padding:10px; background:#161616; border-radius:6px; margin-bottom:8px; }
    .dot { width:10px; height:10px; border-radius:50%; }
    .dot.active { background:#00ff88; } .dot.inactive { background:#ff4455; }
    .logs { background:#0a0a0a; border:1px solid #222; border-radius:6px; padding:14px; height:200px; overflow-y:auto; font-size:11px; }
    .log-line { padding:2px 0; border-bottom:1px solid #0f0f0f; }
    .back { color:#00ff88; text-decoration:none; font-size:12px; }
    table { width:100%; border-collapse:collapse; font-size:12px; }
    th { color:#666; text-align:left; padding:8px; border-bottom:1px solid #222; font-size:11px; }
    td { padding:8px; border-bottom:1px solid #111; }
  </style>
</head>
<body>
  <a class="back" href="/">← Back to Dashboard</a>
  <h1 style="margin-top:16px;">📊 Full Status Report</h1>
  <div style="color:#666;font-size:11px;">{{ now }} · auto-refresh 30s</div>

  <h2>🔧 SERVICES</h2>
  <div class="service">
    <div class="dot {{ 'active' if learner == 'active' else 'inactive' }}"></div>
    <span>Strategy Learner</span>
    <span class="{{ 'green' if learner == 'active' else 'red' }}" style="margin-left:auto;">{{ learner.upper() }}</span>
  </div>
  <div class="service">
    <div class="dot {{ 'active' if dashboard == 'active' else 'inactive' }}"></div>
    <span>Web Dashboard</span>
    <span class="{{ 'green' if dashboard == 'active' else 'red' }}" style="margin-left:auto;">{{ dashboard.upper() }}</span>
  </div>
  <div class="service">
    <div class="dot {{ 'active' if trader == 'active' else 'inactive' }}"></div>
    <span>Trading Bot</span>
    <span class="{{ 'green' if trader == 'active' else 'red' }}" style="margin-left:auto;">{{ trader.upper() }}</span>
  </div>

  <h2>🤖 STRATEGY LEARNER</h2>
  <div class="grid">
    <div class="card"><div class="label">TOTAL DISCOVERED</div><div class="value blue">{{ total }}</div></div>
    <div class="card"><div class="label">HIGH QUALITY (60+)</div><div class="value green">{{ high }}</div></div>
    <div class="card"><div class="label">BEST SCORE</div><div class="value yellow">{{ best_score }}</div></div>
  </div>

  <h2>💹 TRADING RESULTS</h2>
  <div class="grid">
    <div class="card"><div class="label">TOTAL P&L</div>
      <div class="value {{ 'green' if pnl >= 0 else 'red' }}">${{ "%.2f"|format(pnl) }}</div></div>
    <div class="card"><div class="label">WINS</div><div class="value green">{{ wins }}</div></div>
    <div class="card"><div class="label">LOSSES</div><div class="value red">{{ losses }}</div></div>
  </div>

  {% if trades %}
  <h2>📋 RECENT TRADES</h2>
  <table>
    <tr><th>Date</th><th>Symbol</th><th>Action</th><th>Price</th><th>P&L</th></tr>
    {% for t in trades[-10:]|reverse %}
    <tr>
      <td style="color:#666;">{{ t.date }} {{ t.time }}</td>
      <td class="blue">{{ t.symbol }}</td>
      <td class="{{ 'green' if t.action == 'BUY' else 'red' }}">{{ t.action }}</td>
      <td>${{ t.price }}</td>
      <td class="{{ 'green' if t.pnl >= 0 else 'red' }}">${{ "%.2f"|format(t.pnl) }}</td>
    </tr>
    {% endfor %}
  </table>
  {% endif %}

  <h2>📋 LEARNER LOGS</h2>
  <div class="logs">
    {% for line in logs %}
    <div class="log-line" style="color:{% if 'ERROR' in line %}#ff4455{% elif 'WARNING' in line %}#ffaa00{% elif 'Saved' in line or 'Exported' in line %}#00ff88{% else %}#00ccff{% endif %}">{{ line }}</div>
    {% endfor %}
  </div>
</body>
</html>
"""
    return render_template_string(STATUS_TEMPLATE,
        now=now, total=total, high=high, best_score=best_score,
        pnl=pnl, wins=wins, losses=losses, trades=trades,
        learner=learner_status, trader=trader_status, dashboard=dashboard_status,
        logs=logs)


@app.route("/")
def index():
    best_data = _load(BEST_FILE, {"strategies": []})
    best      = best_data.get("strategies", [])[:10]

    all_scores = _load(SCORES_FILE, {})
    total      = len(_load(STRATEGIES_FILE, {}))
    high       = sum(1 for s in all_scores.values() if s >= 60)
    avg        = round(sum(all_scores.values()) / max(total, 1), 1) if all_scores else 0
    best_score = max(all_scores.values()) if all_scores else 0

    logs = get_last_logs(60)
    now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    stats = {
        "total":        total,
        "high_quality": high,
        "avg_score":    avg,
        "best_score":   best_score,
    }

    return render_template_string(TEMPLATE, best=best, stats=stats, logs=logs, now=now)


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", 5000))
    print(f"\n✅ Dashboard running at http://0.0.0.0:{port}")
    print(f"   Access via: http://35.177.54.44:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
