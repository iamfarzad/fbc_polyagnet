import gradio as gr
import json
import os
import time
import datetime
import sys
from dotenv import load_dotenv

# Add agents path for Polymarket wrapper
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agents.polymarket.polymarket import Polymarket

# Load env for balance check
load_dotenv()

pm = Polymarket()

def get_state(file_name):
    if os.path.exists(file_name):
        try:
            with open(file_name, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def update_dashboard():
    safe_state = get_state("safe_state.json") or {}
    scalper_state = get_state("scalper_state.json") or {}
    
    # Balance
    try:
        balance = pm.get_usdc_balance()
    except:
        balance = 10.95 # Fallback for demo if API fails
        
    prices = scalper_state.get("prices", {})
    price_md = ""
    for k, v in prices.items():
        price_md += f"**{k}**: {v:.3f}  \n"
    
    return (
        f"${balance:.2f} USDC",
        safe_state.get("status", "Idle"),
        safe_state.get("last_decision", "None"),
        f"{safe_state.get('confidence', 0)*100:.1f}%" if "confidence" in safe_state else "N/A",
        price_md or "Waiting for WS data...",
        scalper_state.get("last_trade", "None"),
        scalper_state.get("last_update", "N/A")
    )

with gr.Blocks(theme="monochrome", title="Polymarket Bot Dashboard") as demo:
    gr.Markdown("# 🤖 Polymarket Bots Monitoring")
    
    with gr.Row():
        balance_val = gr.Textbox(label="Wallet Balance", value="Loading...", interactive=False)
        last_upd = gr.Textbox(label="Last Scalper Refresh", value="N/A", interactive=False)

    with gr.Row():
        with gr.Column():
            gr.Markdown("### 🛡️ Safe Agent (Polling)")
            s_status = gr.Textbox(label="Current Status", interactive=False)
            s_decision = gr.Textbox(label="Last Decision", interactive=False)
            s_conf = gr.Textbox(label="LLM Confidence", interactive=False)
            
        with gr.Column():
            gr.Markdown("### ⚡ Crypto Scalper (WS)")
            sc_prices = gr.Markdown("Waiting for prices...")
            sc_trade = gr.Textbox(label="Last Trade", interactive=False)

    # Auto-refresh logic (Gradio 3 style)
    demo.load(update_dashboard, None, [balance_val, s_status, s_decision, s_conf, sc_prices, sc_trade, last_upd], every=5)

if __name__ == "__main__":
    # Fly.io expects 0.0.0.0 and port 8080 or as configured
    port = int(os.getenv("PORT", 7860))
    demo.queue().launch(server_name="0.0.0.0", server_port=port)
