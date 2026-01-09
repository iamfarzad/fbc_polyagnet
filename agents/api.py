
import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Import existing agent logic
import sys
# Ensure agents package is resolvable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Polymarket - try different paths for local vs Fly.io
try:
    from agents.polymarket.polymarket import Polymarket
    from agents.utils.risk_engine import check_drawdown
except ImportError:
    try:
        from agents.agents.polymarket.polymarket import Polymarket
        from agents.agents.utils.risk_engine import check_drawdown
    except ImportError:
        # Fallback: define stub
        Polymarket = None
        check_drawdown = lambda *args: False 

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("API")

load_dotenv()

app = FastAPI(title="Polymarket Agent Dashboard API")

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, lock this down
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- State Management ---
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_state.json")

def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
    # Default State
    return {
        "safe_running": False,
        "scalper_running": False,
        "copy_trader_running": False,
        "dry_run": True,
        "safe_last_activity": "Idle",
        "safe_last_endpoint": "-",
        "scalper_last_activity": "Idle",
        "scalper_last_endpoint": "-",
        "last_signal": "None"
    }

def save_state(state: Dict[str, Any]):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")

# --- Polymarket Client ---
# Initialize globally. In a real app, might want dependency injection or per-request if stateful.
# Polymarket class is mostly stateless wrappers + private key.
try:
    pm = Polymarket()
    logger.info("Polymarket Client Initialized")
except Exception as e:
    logger.error(f"Failed to init Polymarket Client: {e}")
    pm = None

# --- Models ---
class AgentToggleRequest(BaseModel):
    agent: str  # "safe", "scalper", "copyTrader"

class DashboardData(BaseModel):
    balance: float
    equity: float
    unrealizedPnl: float
    gasSpent: float
    riskStatus: Dict[str, Any] # {safe: bool, message: str}
    agents: Dict[str, Dict[str, Any]]
    positions: List[Dict[str, Any]]
    trades: List[Dict[str, Any]]
    stats: Dict[str, Any]
    dryRun: bool
    lastUpdate: str
    walletAddress: str  # Bot's wallet address

# --- Helper Functions ---
def fetch_positions_helper():
    if not pm: return []
    try:
        # PM Data API for positions
        url = f"https://data-api.polymarket.com/positions?user={pm.get_address_for_private_key()}"
        # using requests inside synch route is blocking, better async or optimized
        # For this scale, it's fine.
        import requests
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            raw = resp.json()
            # Transform to UI model
            positions = []
            for p in raw:
                try:
                    market = p.get("title", p.get("question", "Unknown"))
                    side = p.get("outcome", "?")
                    cost = float(p.get("cost", 0))
                    val = float(p.get("currentValue", p.get("value", 0)))
                    pnl = val - cost
                    positions.append({
                        "market": market,
                        "side": side,
                        "cost": cost,
                        "value": val,
                        "pnl": pnl
                    })
                except: continue
            return positions
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
    return []

def fetch_trades_helper(limit=50):
    if not pm: return []
    try:
        url = f"https://data-api.polymarket.com/trades?user={pm.get_address_for_private_key()}&limit={limit}"
        import requests
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            raw = resp.json()
            trades = []
            for t in raw:
                try:
                    ts = t.get("timestamp", str(datetime.now()))
                    # Format timestamp if needed, or pass raw string
                    # API returns Unix or ISO? Check docs/dash. Usually ISO or int.
                    # Previous dashboard code implies it's a timestamp string.
                    trades.append({
                        "time": str(ts), 
                        "market": t.get("title", t.get("question", "N/A")),
                        "side": t.get("side", t.get("outcome", "?")),
                        "amount": float(t.get("amount", t.get("size", 0))) * float(t.get("price", 0)) # Value? Or just amount?
                        # user interface expects "amount" (USD value usually)
                    })
                except: continue
            return trades
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
    return []

# --- Endpoints ---

@app.get("/api/dashboard", response_model=DashboardData)
def get_dashboard():
    state = load_state()
    
    # 1. Balance
    balance = 0.0
    if pm:
        try:
            balance = pm.get_usdc_balance()
        except: pass
        
    # 2. Positions & Equity
    positions = fetch_positions_helper()
    unrealized_pnl = sum(p['pnl'] for p in positions)
    equity = balance + unrealized_pnl # Simplified equity (cash + open pnl? Or cash + open value?)
    # Equity usually = Cash + Market Value of Positions
    market_value = sum(p['value'] for p in positions)
    equity = balance + market_value 

    # 3. Trades
    trades = fetch_trades_helper(limit=10) # Minimal for dashboard
    
    # 4. Global Stats
    # We can fetch count from total trades or state
    all_trades = fetch_trades_helper(limit=100)
    trade_count = len(all_trades)
    vol_24h = sum(t['amount'] for t in all_trades) # Rough approx
    
    # 5. Risk Status
    # Replicate logic: < $3.0 is "Low Balance/Drawdown" warning
    # Or ideally, track drawdowns via state. For now, simple check.
    risk_safe = balance > 3.0
    risk_msg = "No Drawdown Detected" if risk_safe else "Low Balance / Drawdown Limit"
    
    # 6. Gas (Mock or fetch)
    # Fetching polygonscan every refresh is heavy. Maybe cache or simple calc.
    # For now, return 0.0 or last known
    gas_spent = 0.0 # Setup proper tracking later
    
    # 7. Agents
    agents_data = {
        "safe": {
            "running": state.get("safe_running", False),
            "activity": state.get("safe_last_activity", "Idle"),
            "endpoint": state.get("safe_last_endpoint", "-")
        },
        "scalper": {
            "running": state.get("scalper_running", False),
            "activity": state.get("scalper_last_activity", "Idle"),
            "endpoint": state.get("scalper_last_endpoint", "-")
        },
        "copyTrader": {
            "running": state.get("copy_trader_running", False),
            "lastSignal": state.get("last_signal", "None")
        }
    }

    # Get wallet address
    wallet_address = ""
    if pm:
        try:
            wallet_address = pm.get_address_for_private_key()
        except: pass

    return {
        "balance": balance,
        "equity": equity,
        "unrealizedPnl": unrealized_pnl,
        "gasSpent": gas_spent,
        "riskStatus": {
            "safe": risk_safe,
            "message": risk_msg
        },
        "agents": agents_data,
        "positions": positions,
        "trades": trades,
        "stats": {
            "tradeCount": trade_count,
            "volume24h": vol_24h
        },
        "dryRun": state.get("dry_run", True),
        "lastUpdate": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "walletAddress": wallet_address
    }

@app.post("/api/toggle-agent")
def toggle_agent(req: AgentToggleRequest):
    state = load_state()
    target = req.agent
    
    if target == "safe":
        state["safe_running"] = not state.get("safe_running", False)
    elif target == "scalper":
        state["scalper_running"] = not state.get("scalper_running", False)
    elif target == "copyTrader":
        state["copy_trader_running"] = not state.get("copy_trader_running", False)
    
    save_state(state)
    return {"status": "success", "state": state}

@app.post("/api/toggle-dry-run")
def toggle_dry_run():
    state = load_state()
    state["dry_run"] = not state.get("dry_run", True)
    save_state(state) # Agents read this file
    return {"status": "success", "dry_run": state["dry_run"]}

@app.post("/api/emergency-stop")
def emergency_stop():
    state = load_state()
    state["safe_running"] = False
    state["scalper_running"] = False
    state["copy_trader_running"] = False
    save_state(state)
    return {"status": "stopped"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
