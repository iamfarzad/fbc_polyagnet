# Runtime patch for huggingface_hub
import huggingface_hub
try:
    from huggingface_hub import HfFolder
except ImportError:
    try:
        from huggingface_hub.utils import HfFolder
        huggingface_hub.HfFolder = HfFolder
    except ImportError:
        pass

import gradio as gr
import os
import sys
import requests
from datetime import datetime
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agents.polymarket.polymarket import Polymarket

load_dotenv()
pm = Polymarket()

# Minimal dark theme CSS
custom_css = """
body { font-family: 'Inter', -apple-system, sans-serif; }
.gradio-container { max-width: 1000px !important; margin: auto !important; }
.stat-box { text-align: center; padding: 1rem; }
.stat-value { font-size: 1.8rem; font-weight: 600; }
.stat-label { font-size: 0.85rem; opacity: 0.7; }
"""

def fetch_positions():
    """Fetch open positions"""
    try:
        url = f"https://gamma-api.polymarket.com/portfolio?user={pm.public_key}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Position fetch error: {e}")
    return []

def fetch_trades():
    """Fetch recent trades"""
    try:
        url = f"https://gamma-api.polymarket.com/trades?user={pm.public_key}&limit=10"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"Trade fetch error: {e}")
    return []

def update_dashboard():
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # 1. Balance
    try:
        balance = pm.get_usdc_balance()
    except:
        balance = 0.0
    
    # 2. Positions & Unrealized PnL
    positions = fetch_positions()
    unrealized = 0.0
    pos_data = []
    
    if positions:
        for p in positions[:10]:
            market = p.get("title", p.get("question", "Unknown"))[:40]
            side = p.get("outcome", "?")
            size = float(p.get("size", 0))
            value = float(p.get("currentValue", p.get("value", 0)))
            cost = float(p.get("cost", size))
            pnl = value - cost
            unrealized += pnl
            pos_data.append([market, side, f"${cost:.2f}", f"${value:.2f}", f"${pnl:+.2f}"])
    
    if not pos_data:
        positions_md = "_No open positions_"
    else:
        positions_md = "| Market | Side | Cost | Value | PnL |\n|--------|------|------|-------|-----|\n"
        for row in pos_data:
            positions_md += f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |\n"
    
    # 3. Total Equity
    equity = balance + unrealized
    
    # 4. Trades
    trades = fetch_trades()
    if trades:
        trades_md = "| Time | Market | Side | Amount |\n|------|--------|------|--------|\n"
        for t in trades[:8]:
            ts = t.get("timestamp", "")[:16]
            market = t.get("title", t.get("question", "N/A"))[:25]
            side = t.get("side", t.get("outcome", "?"))
            amt = float(t.get("amount", t.get("size", 0)))
            trades_md += f"| {ts} | {market}... | {side} | ${amt:.2f} |\n"
    else:
        trades_md = "_No recent trades_"
    
    # 5. PnL summary
    pnl_color = "🟢" if unrealized >= 0 else "🔴"
    
    return (
        f"${balance:.2f}",
        f"${equity:.2f}",
        f"{pnl_color} ${unrealized:+.2f}",
        positions_md,
        trades_md,
        now
    )

with gr.Blocks(theme=gr.themes.Soft(), css=custom_css, title="Polymarket Dashboard") as demo:
    gr.Markdown("# 📊 Polymarket Bot Monitor")
    
    with gr.Row():
        balance_box = gr.Textbox(label="💵 USDC Balance", value="...", interactive=False)
        equity_box = gr.Textbox(label="💰 Total Equity", value="...", interactive=False)
        pnl_box = gr.Textbox(label="📈 Unrealized PnL", value="...", interactive=False)
    
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 📋 Open Positions")
            positions_md = gr.Markdown("_Loading..._")
        with gr.Column():
            gr.Markdown("### 🕐 Recent Trades")
            trades_md = gr.Markdown("_Loading..._")
    
    gr.Markdown("---")
    refresh_time = gr.Markdown("_Last updated: ..._")
    
    def format_refresh(bal, eq, pnl, pos, trades, ts):
        return bal, eq, pnl, pos, trades, f"_Last updated: {ts}_"
    
    demo.load(
        lambda: format_refresh(*update_dashboard()),
        None,
        [balance_box, equity_box, pnl_box, positions_md, trades_md, refresh_time],
        every=10
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
