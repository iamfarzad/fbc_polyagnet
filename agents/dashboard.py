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

# Custom CSS for minimal modern look
custom_css = """
body { font-family: 'Inter', -apple-system, sans-serif; }
.gradio-container { max-width: 900px !important; margin: auto !important; }
.gr-box { border-radius: 12px !important; border: 1px solid #222 !important; }
.gr-panel { background: #0a0a0a !important; }
h1 { font-weight: 300 !important; letter-spacing: -1px; }
"""

def fetch_positions():
    """Fetch open positions from Gamma API"""
    try:
        url = f"https://gamma-api.polymarket.com/portfolio/{pm.public_key}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("positions", [])
    except:
        pass
    return []

def fetch_recent_trades():
    """Fetch recent trades from Gamma API"""
    try:
        url = f"https://gamma-api.polymarket.com/trades?user={pm.public_key}&limit=5"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return []

def update_dashboard():
    # 1. Balance
    try:
        balance = pm.get_usdc_balance()
    except:
        balance = 0.0
    
    # 2. Open Positions
    positions = fetch_positions()
    if positions:
        pos_md = "| Market | Side | Size | Value |\n|--------|------|------|-------|\n"
        for p in positions[:5]:
            q = p.get("question", "N/A")[:30]
            side = p.get("outcome", "?")
            size = p.get("size", 0)
            val = p.get("value", 0)
            pos_md += f"| {q}... | {side} | {size:.2f} | ${val:.2f} |\n"
    else:
        pos_md = "_No open positions_"
    
    # 3. Recent Trades
    trades = fetch_recent_trades()
    if trades:
        trade_md = "| Time | Market | Side | Amount |\n|------|--------|------|--------|\n"
        for t in trades[:5]:
            ts = t.get("timestamp", "")[:16]
            q = t.get("question", "N/A")[:25]
            side = t.get("side", "?")
            amt = t.get("amount", 0)
            trade_md += f"| {ts} | {q}... | {side} | ${amt:.2f} |\n"
    else:
        trade_md = "_No recent trades_"
    
    # 4. Bot Status (simple check based on time)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    return (
        f"${balance:.2f}",
        pos_md,
        trade_md,
        now
    )

with gr.Blocks(theme=gr.themes.Soft(), css=custom_css, title="Polymarket Dashboard") as demo:
    gr.Markdown("# Polymarket Bot Monitor")
    gr.Markdown("_Live view of your trading activity_")
    
    with gr.Row():
        balance_box = gr.Textbox(label="💰 USDC Balance", value="...", interactive=False, scale=1)
        refresh_time = gr.Textbox(label="🕐 Last Refresh", value="...", interactive=False, scale=2)
    
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 📊 Open Positions")
            positions_md = gr.Markdown("_Loading..._")
        with gr.Column():
            gr.Markdown("### 📜 Recent Trades")
            trades_md = gr.Markdown("_Loading..._")
    
    demo.load(update_dashboard, None, [balance_box, positions_md, trades_md, refresh_time], every=10)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
