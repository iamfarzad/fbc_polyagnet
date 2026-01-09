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
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from web3 import Web3, HTTPProvider

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agents.polymarket.polymarket import Polymarket

load_dotenv()
pm = Polymarket()

# Polygon RPC
WEB3_RPC = "https://polygon-rpc.com"  
w3 = Web3(HTTPProvider(WEB3_RPC))
WALLET_ADDRESS = pm.get_address_for_private_key().lower()

# State Management
STATE_FILE = "bot_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"safe_running": True, "scalper_running": True, "copy_trader_running": False, "dry_run": True}

def save_state(safe_running, scalper_running, copy_trader_running, dry_run):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({
                "safe_running": safe_running,
                "scalper_running": scalper_running,
                "copy_trader_running": copy_trader_running,
                "dry_run": dry_run
            }, f)
    except Exception as e:
        print(f"Error saving state: {e}")

# Initial Load
state = load_state()
SAFE_RUNNING = state.get("safe_running", True)
SCALPER_RUNNING = state.get("scalper_running", True)

# Minimal dark CSS
custom_css = """
body { font-family: 'Inter', sans-serif; background: #0f0f0f; color: #e0e0e0; }
.gradio-container { max-width: 1200px; margin: auto; padding: 20px; }
h1 { text-align: center; font-weight: 600; }
.row { margin-bottom: 20px; }
.stat-card { background: #1a1a1a; padding: 15px; border-radius: 8px; text-align: center; }
.button { background: #333; color: #fff; border: none; border-radius: 4px; padding: 10px; }
"""

def fetch_positions():
    try:
        url = f"https://data-api.polymarket.com/positions?user={pm.get_address_for_private_key()}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return []

def fetch_trades():
    try:
        url = f"https://data-api.polymarket.com/trades?user={pm.get_address_for_private_key()}&limit=50"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return []

def fetch_transactions(limit=20):
    """Fetch last txns for wallet with Polygonscan links"""
    txns = []
    try:
        api_key = os.getenv("POLYGONSCAN_API_KEY") 
        if not api_key:
             # Fallback to purely functional if no API key, but user requested history.
             # Without API key, we can't easily get simplified tx list from RPC comfortably.
             return "Polygonscan API key missing in .env. Please add POLYGONSCAN_API_KEY."
        
        url = f"https://api.polygonscan.com/api?module=account&action=txlist&address={WALLET_ADDRESS}&sort=desc&apikey={api_key}"
        resp = requests.get(url).json()
        if resp['status'] == '1':
            for tx in resp['result'][:limit]:
                ts = datetime.fromtimestamp(int(tx['timeStamp'])).strftime("%Y-%m-%d %H:%M")
                value_wei = float(tx['value'])
                value = value_wei / 10**18 if value_wei > 0 else 0
                gas_used = float(tx['gasUsed'])
                gas_price = float(tx['gasPrice'])
                gas_fee = (gas_used * gas_price) / 10**18
                
                status = "✅" if tx['isError'] == '0' else "❌"
                tx_hash = tx['hash']
                link = f"https://polygonscan.com/tx/{tx_hash}"
                
                # Try to guess type
                method = tx.get('functionName', '')
                if 'approve' in method.lower(): type_lbl = "Approve"
                elif 'transfer' in method.lower(): type_lbl = "Transfer"
                elif 'order' in method.lower() or 'trade' in method.lower(): type_lbl = "Trade"
                elif value > 0: type_lbl = "Transfer"
                else: type_lbl = "Contract Call"

                txns.append([ts, type_lbl, f"{value:.4f} MATIC", f"{gas_fee:.5f} MATIC", status, f"[View]({link})"])
    except Exception as e:
        return f"Txn fetch error: {str(e)}"
    
    if not txns:
        return "No recent transactions found"
    
    md = "| Time | Type | Value | Fee | Status | Link |\n|------|------|-------|-----|--------|------|\n"
    for row in txns:
        md += f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} |\n"
    return md

def update_dashboard():
    global SAFE_RUNNING, SCALPER_RUNNING, COPY_RUNNING
    
    state = load_state()
    SAFE_RUNNING = state.get("safe_running", True)
    SCALPER_RUNNING = state.get("scalper_running", True)
    COPY_RUNNING = state.get("copy_trader_running", False)
    
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Balance
    try:
        balance = pm.get_usdc_balance()
    except:
        balance = 0.0
        
    # Check Drawdown logic (mirroring agents)
    # We don't have the "Initial Balance" of the agents here easily unless we store it in state or hardcode a "starting bankroll".
    # For now, let's just check if balance < threshold as a rough "Risk Status" or read from state if agents report "Risk Paused".
    # Agents don't write "Risk Paused" to global state yet, but they might log it.
    # Let's assume > $3.0 is "Safe".
    risk_status_lbl = "🟢 Risk Safe" if balance > 3.0 else "⚠️ Low Balance"
    risk_sub = "No Drawdown" if balance > 3.0 else "Drawdown / Low Funds"
    
    # Gas Spent Calculation
    gas_spent_matic = 0.0
    gas_txns = fetch_transactions(limit=100) # Fetch more for calc
    if isinstance(gas_txns, str): # Error message
        gas_spent_txt = "Error"
    else:
        # Re-fetch raw list logic (duplicate but safe for simple dashboard)
        try:
             # Just parse the md roughly or refactor fetch_transactions to return list+md
             # For speed, let's reuse the logic since we can't easily change signature wildly without breaking
             # Actually, better to refactor fetch_transactions to return data and md separately?
             # Let's keep it simple: Add a helper or just parse if needed. 
             # Or better: Extract logic.
             pass
        except: pass
    
    # Refactored Logic for Gas
    total_gas = 0.0
    try:
        api_key = os.getenv("POLYGONSCAN_API_KEY")
        if api_key:
             url = f"https://api.polygonscan.com/api?module=account&action=txlist&address={WALLET_ADDRESS}&sort=desc&apikey={api_key}"
             r = requests.get(url).json()
             if r['status'] == '1':
                 for tx in r['result']:
                     gas_used = float(tx['gasUsed'])
                     gas_price = float(tx['gasPrice'])
                     total_gas += (gas_used * gas_price) / 10**18
    except: pass
    
    gas_display = f"{total_gas:.4f} POL"
    unrealized = 0.0
    pos_data = []
    if positions:
        for p in positions[:10]:
            try:
                market = p.get("title", p.get("question", "Unknown"))[:40]
                side = p.get("outcome", "?")
                cost = float(p.get("cost", 0))
                value = float(p.get("currentValue", p.get("value", 0)))
                pnl = value - cost
                unrealized += pnl
                pos_data.append([market, side, f"${cost:.2f}", f"${value:.2f}", f"${pnl:.2f}"])
            except: continue
    
    if not pos_data:
        positions_md = "*No open positions*"
    else:
        positions_md = "| Market | Side | Cost | Value | PnL |\n|--------|------|------|-------|-----|\n"
        for row in pos_data:
            positions_md += f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |\n"
    
    # Equity
    equity = balance + unrealized
    
    # Trades & Stats
    trades = fetch_trades() # Update to limit=50 in definition or arg? default is 20. Update def below.
    trade_count = len(trades)
    volume_24h = 0.0
    
    if not trades:
        trades_md = "*No recent trades*"
    else:
        trades_md = "| Time | Market | Side | Amount |\n|------|--------|------|--------|\n"
        for t in trades[:10]: # Show top 10
            try:
                ts = t.get("timestamp", "")[:16]
                market = t.get("title", t.get("question", "N/A"))[:25]
                side = t.get("side", t.get("outcome", "?"))
                amt = float(t.get("amount", t.get("size", 0))) 
                price = float(t.get("price", 0))
                val = amt * price
                volume_24h += val
                
                trades_md += f"| {ts} | {market} | {side} | ${amt:.2f} |\n"
            except: continue

    stats_txt = f"Trades: {trade_count}\nVol: ${volume_24h:.2f}"
    
    # Transactions
    txns_md = fetch_transactions()

    # Status Strings
    safe_status = "🟢 Active" if SAFE_RUNNING else "🔴 Paused"
    scalper_status = "🟢 Active" if SCALPER_RUNNING else "🔴 Paused"
    copy_status = "🟢 Active" if COPY_RUNNING else "🔴 Paused"
    
    # Activity
    safe_act = state.get("safe_last_activity", "Idle")
    safe_end = state.get("safe_last_endpoint", "-")
    scalper_act = state.get("scalper_last_activity", "Idle")
    scalper_end = state.get("scalper_last_endpoint", "-")
    copy_last = state.get("last_signal", "None")
    
    safe_txt = f"{safe_status}\nAction: {safe_act}\nAPI: {safe_end}"
    scalper_txt = f"{scalper_status}\nAction: {scalper_act}\nAPI: {scalper_end}"
    copy_txt = f"{copy_status}\nLast Signal: {copy_last}"

    # Risk Display
    risk_txt = f"{risk_status_lbl}\n{risk_sub}"
    
    # Button Labels
    safe_btn_label = "Stop Safe Agent" if SAFE_RUNNING else "Start Safe Agent"
    scalper_btn_label = "Stop Scalper" if SCALPER_RUNNING else "Start Scalper"
    copy_btn_label = "Stop Copy Trader" if COPY_RUNNING else "Start Copy Trader"
    
    # Dry Run Status
    dry_run = state.get("dry_run", True)
    dry_txt = "🧪 DRY RUN" if dry_run else "💸 REAL MONEY"
    
    pnl_display = f"🟢 +${unrealized:.2f}" if unrealized >= 0 else f"🔴 -${abs(unrealized):.2f}"
    
    return (
        f"${balance:.2f}",
        f"${equity:.2f}",
        pnl_display,
        stats_txt,
        gas_display,
        risk_txt,
        safe_txt,
        scalper_txt,
        copy_txt,
        positions_md,
        trades_md,
        txns_md,
        f"Last Updated: {now} | Mode: {dry_txt}",
        safe_btn_label,
        scalper_btn_label,
        copy_btn_label,
        dry_run
    )

def toggle_safe():
    global SAFE_RUNNING
    state = load_state()
    new_state = not state.get("safe_running", True)
    save_state(new_state, state.get("scalper_running", True), state.get("dry_run", True))
    SAFE_RUNNING = new_state
    # Force immediate update return
    return update_dashboard()

def toggle_scalper():
    global SCALPER_RUNNING
    state = load_state()
    new_state = not state.get("scalper_running", True)
    save_state(state.get("safe_running", True), new_state, state.get("dry_run", True))
    SCALPER_RUNNING = new_state
    return update_dashboard()

with gr.Blocks(theme=gr.themes.Glass(), css=custom_css, title="Polymarket Dashboard") as demo:
    gr.Markdown("# Polymarket Bot Monitor")
    
    with gr.Row():
        balance_box = gr.Textbox(label="USDC Balance", interactive=False)
        equity_box = gr.Textbox(label="Total Equity", interactive=False)
        pnl_box = gr.Textbox(label="Unrealized PnL", interactive=False)
        stats_box = gr.Textbox(label="Activity (Last 50)", interactive=False)
        gas_box = gr.Textbox(label="Est. Gas Spent", interactive=False)
    
    with gr.Row():
        safe_status_box = gr.Textbox(label="Safe Agent Status", interactive=False)
        scalper_status_box = gr.Textbox(label="Scalper Status", interactive=False)
        copy_status_box = gr.Textbox(label="Copy Trader Status", interactive=False)
    
    with gr.Row():
        safe_btn = gr.Button("Toggle Safe Agent")
        scalper_btn = gr.Button("Toggle Scalper")
        copy_btn = gr.Button("Toggle Copy Trader")
    
    with gr.Row():
        kill_btn = gr.Button("🚨 EMERGENCY STOP ALL", variant="stop")
        dry_run_chk = gr.Checkbox(label="Global Dry Run Mode", value=True)
    
    with gr.Row():
        with gr.Column():
            gr.Markdown("### Open Positions")
            positions_md = gr.Markdown()
        with gr.Column():
            gr.Markdown("### Recent Trades")
            trades_md = gr.Markdown()
    
    gr.Markdown("### Transaction History (Polygonscan)")
    txns_md = gr.Markdown()
    
    with gr.Row():
        gr.Markdown(f"🔗 [View Wallet on Polygonscan](https://polygonscan.com/address/{WALLET_ADDRESS})", elem_classes="footer")
        refresh_time = gr.Markdown(elem_id="footer")
    
    # Event wiring
    outputs = [
        balance_box, equity_box, pnl_box, stats_box, gas_box, risk_box,
        safe_status_box, scalper_status_box, copy_status_box,
        positions_md, trades_md, txns_md, 
        refresh_time,
        safe_btn, scalper_btn, copy_btn,
        dry_run_chk
    ]
    
    
    # Emergency Controls
    kill_btn.click(emergency_kill, None, outputs)
    dry_run_chk.change(toggle_dry_run, None, outputs)
    
    safe_btn.click(toggle_safe, None, outputs)
    scalper_btn.click(toggle_scalper, None, outputs)
    copy_btn.click(toggle_copy, None, outputs)
    
    demo.load(update_dashboard, None, outputs, every=30)

if __name__ == "__main__":
    # Init state file if missing
    if not os.path.exists(STATE_FILE):
        save_state(True, True, False, True)
        
    port = int(os.getenv("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)
