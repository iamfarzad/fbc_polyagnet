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

# Sleek dark theme CSS
custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important; }

body { background: #0a0a0a !important; }

.gradio-container { 
    max-width: 1100px !important; 
    margin: auto !important;
    background: linear-gradient(180deg, #111 0%, #0a0a0a 100%) !important;
    border-radius: 16px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4) !important;
    padding: 2rem !important;
}

h1 { 
    font-weight: 700 !important; 
    letter-spacing: -0.5px !important;
    background: linear-gradient(90deg, #fff, #888) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
}

.block { 
    background: rgba(255,255,255,0.02) !important; 
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 12px !important;
    backdrop-filter: blur(10px) !important;
}

input, textarea {
    background: rgba(0,0,0,0.3) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
    color: #fff !important;
}

.markdown-text { color: rgba(255,255,255,0.85) !important; }

table { 
    width: 100% !important;
    border-collapse: collapse !important;
}

th { 
    background: rgba(255,255,255,0.05) !important;
    padding: 12px !important;
    text-align: left !important;
    font-weight: 600 !important;
    border-bottom: 1px solid rgba(255,255,255,0.1) !important;
}

td { 
    padding: 10px 12px !important;
    border-bottom: 1px solid rgba(255,255,255,0.05) !important;
}

.stat-card {
    background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02)) !important;
    border-radius: 12px !important;
    padding: 1.5rem !important;
    text-align: center !important;
}
"""

def fetch_positions():
    try:
        url = f"https://gamma-api.polymarket.com/portfolio?user={pm.public_key}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return []

def fetch_trades():
    try:
        url = f"https://gamma-api.polymarket.com/trades?user={pm.public_key}&limit=10"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return []

# Cache for allowance to avoid spamming RPC
_allowance_cache = {"value": None, "last_updated": 0}

def get_cached_allowance():
    now = time.time()
    if _allowance_cache["value"] is None or (now - _allowance_cache["last_updated"] > 300):
        try:
            val = pm.get_usdc_allowance()
            _allowance_cache["value"] = val
            _allowance_cache["last_updated"] = now
        except:
            return 0.0
    return _allowance_cache["value"]

def update_dashboard():
    now = datetime.utcnow().strftime("%H:%M:%S UTC")
    
    try:
        balance = pm.get_usdc_balance()
    except:
        balance = 0.0
        
    try:
        allowance = get_cached_allowance()
        status = "✅ Active" if allowance > 500 else "⚠️ Approval Needed"
    except:
        status = "Unknown"
    
    positions = fetch_positions()
    unrealized = 0.0
    pos_data = []
    
    if positions:
        for p in positions[:10]:
            try:
                market = p.get("title", p.get("question", "Unknown"))[:35]
                side = p.get("outcome", "?")
                size = float(p.get("size", 0))
                value = float(p.get("currentValue", p.get("value", 0)))
                cost = float(p.get("cost", size)) # Fallback if cost missing
                pnl = value - cost
                unrealized += pnl
                pos_data.append([market, side, f"${cost:.2f}", f"${value:.2f}", f"${pnl:+.2f}"])
            except Exception as e:
                print(f"Error parsing position: {e}")
                continue
    
    if not pos_data:
        positions_md = "*No open positions*"
    else:
        positions_md = "| Market | Side | Cost | Value | PnL |\n|:-------|:-----|-----:|------:|----:|\n"
        for row in pos_data:
            positions_md += f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |\n"
    
    equity = balance + unrealized
    
    trades = fetch_trades()
    if trades:
        trades_md = "| Time | Market | Side | Size |\n|:-----|:-------|:-----|-----:|\n"
        for t in trades[:6]:
            try:
                ts = t.get("timestamp", "")[:16]
                market = t.get("title", t.get("question", "N/A"))[:20]
                side = t.get("side", t.get("outcome", "?"))
                amt = float(t.get("amount", t.get("size", 0)))
                trades_md += f"| {ts} | {market}... | {side} | ${amt:.2f} |\n"
            except:
                continue
    else:
        trades_md = "*No recent trades*"
    
    pnl_display = f"${unrealized:+.2f}" if unrealized != 0 else "$0.00"
    
    return (
        f"${balance:.2f}",
        f"${equity:.2f}",
        pnl_display,
        status,
        positions_md,
        trades_md,
        f"Updated {now}"
    )

with gr.Blocks(theme=gr.themes.Glass(), css=custom_css, title="Polymarket Dashboard") as demo:
    gr.Markdown("# Polymarket Bot Monitor")
    
    with gr.Row(equal_height=True):
        balance_box = gr.Textbox(label="USDC Balance", value="...", interactive=False, elem_classes="stat-card")
        equity_box = gr.Textbox(label="Total Equity", value="...", interactive=False, elem_classes="stat-card")
        pnl_box = gr.Textbox(label="Unrealized PnL", value="...", interactive=False, elem_classes="stat-card")
        status_box = gr.Textbox(label="Trading Status", value="Checking...", interactive=False, elem_classes="stat-card")
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Open Positions")
            positions_md = gr.Markdown("*Loading...*")
        with gr.Column(scale=1):
            gr.Markdown("### Recent Trades")
            trades_md = gr.Markdown("*Loading...*")
    
    refresh_time = gr.Markdown("*Connecting...*", elem_classes="footer")
    
    demo.load(
        update_dashboard,
        None,
        [balance_box, equity_box, pnl_box, status_box, positions_md, trades_md, refresh_time],
        every=10
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
