
import os
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi import WebSocket, WebSocketDisconnect
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
    from agents.utils.context import get_context
except ImportError:
    try:
        from agents.agents.polymarket.polymarket import Polymarket
        from agents.agents.utils.risk_engine import check_drawdown
        from agents.agents.utils.context import get_context
    except ImportError:
        # Fallback: define stub
        Polymarket = None
        check_drawdown = lambda *args: False
        get_context = None 

# Import Supabase for shared state
try:
    from agents.utils.supabase_client import get_supabase_state
    HAS_SUPABASE = True
except ImportError:
    try:
        from agents.agents.utils.supabase_client import get_supabase_state
        HAS_SUPABASE = True
    except ImportError:
        HAS_SUPABASE = False
        get_supabase_state = None 

# Setup Logging
print("VERSION DEBUG: MAX BET ENABLED")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("API")

load_dotenv()

# Dashboard wallet address - use Proxy for position tracking after consolidation
# Falls back to deriving from private key if not set
DASHBOARD_WALLET = os.getenv("DASHBOARD_WALLET", "0xdb1f88Ab5B531911326788C018D397d352B7265c")

app = FastAPI(title="Polymarket Agent Dashboard API")

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, lock this down
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# WebSocket streams (simple, no overengineering)
# =============================================================================

def _safe_json(obj: Any) -> Any:
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_json(v) for v in obj]
    return str(obj)


@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket):
    """
    Push dashboard payloads over WS.
    Frontend can stop polling when connected.
    """
    await ws.accept()
    try:
        while True:
            payload = None
            try:
                payload = get_dashboard(background_tasks=BackgroundTasks())
            except Exception as e:
                payload = {"error": str(e)}
            await ws.send_json(_safe_json(payload))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
    except Exception:
        return


@app.websocket("/ws/llm-activity")
async def ws_llm_activity(ws: WebSocket):
    """Push LLM activity payload over WS."""
    await ws.accept()
    try:
        while True:
            payload = None
            try:
                payload = get_llm_activity(limit=50, agent=None)
            except Exception as e:
                payload = {"activities": [], "stats": {}, "error": str(e)}
            await ws.send_json(_safe_json(payload))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
    except Exception:
        return

# --- State Management ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "bot_state.json")
SAFE_STATE_FILE = os.path.join(BASE_DIR, "safe_state.json")
SCALPER_STATE_FILE = os.path.join(BASE_DIR, "scalper_state.json")
COPY_STATE_FILE = os.path.join(BASE_DIR, "copy_state.json")
SNAPSHOTS_FILE = os.path.join(BASE_DIR, "snapshots.json")

def load_agent_state(filepath: str) -> Dict[str, Any]:
    """Load state from an agent-specific file."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def load_state() -> Dict[str, Any]:
    """Load and aggregate state from all sources."""
    # Load master state (control flags)
    master = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                master = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            
    # Auto-detect Production Environment (Fly.io)
    # If running in cloud, default to LIVE unless explicitly overridden in file
    if os.getenv("FLY_APP_NAME") and "dry_run" not in master:
        master["dry_run"] = False
    
    # Load individual agent states
    safe_state = load_agent_state(SAFE_STATE_FILE)
    scalper_state = load_agent_state(SCALPER_STATE_FILE)
    copy_state = load_agent_state(COPY_STATE_FILE)
    
    # Aggregate into unified state
    return {
        # Control flags from master
        "safe_running": master.get("safe_running", False),
        "scalper_running": master.get("scalper_running", False),
        "copy_trader_running": master.get("copy_trader_running", False),
        "smart_trader_running": master.get("smart_trader_running", True),
        "esports_trader_running": master.get("esports_trader_running", True),
        "dry_run": master.get("dry_run", True),
        "dynamic_max_bet": master.get("dynamic_max_bet", 0.50),
        
        # Safe agent activity
        "safe_last_activity": safe_state.get("last_decision", 
                             safe_state.get("status", 
                             master.get("safe_last_activity", "Idle"))),
        "safe_last_endpoint": safe_state.get("safe_last_endpoint", 
                             master.get("safe_last_endpoint", "Gamma API")),
        
        # Scalper activity
        "scalper_last_activity": scalper_state.get("scalper_last_activity",
                                scalper_state.get("last_trade",
                                master.get("scalper_last_activity", "Idle"))),
        "scalper_last_endpoint": scalper_state.get("scalper_last_endpoint",
                                master.get("scalper_last_endpoint", "-")),
        "scalper_prices": scalper_state.get("prices", {}),
        "scalper_markets": scalper_state.get("active_markets", 0),
        
        # Copy trader activity  
        "last_signal": copy_state.get("last_signal",
                      master.get("last_signal", "None")),
        "copy_last_scan": copy_state.get("last_scan", "-"),
        
        # === GAP FIX: Heartbeat tracking for agent health ===
        "safe_heartbeat": safe_state.get("heartbeat", master.get("safe_heartbeat")),
        "scalper_heartbeat": scalper_state.get("heartbeat", master.get("scalper_heartbeat")),
        "copy_heartbeat": copy_state.get("heartbeat", master.get("copy_heartbeat")),
    }

def save_state(state: Dict[str, Any]):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")

# --- Polymarket Client ---
# Lazy initialization to avoid blocking app startup
_pm_instance = None
_pm_init_attempted = False

def get_pm():
    """Lazy-load Polymarket client on first use."""
    global _pm_instance, _pm_init_attempted
    if _pm_instance is None and not _pm_init_attempted:
        _pm_init_attempted = True
        try:
            _pm_instance = Polymarket()
            logger.info("Polymarket Client Initialized (lazy)")
        except Exception as e:
            logger.error(f"Failed to init Polymarket Client: {e}")
    return _pm_instance

# For backwards compatibility
pm = None  # Will be None at startup, use get_pm() instead

# --- Health Check (doesn't require Polymarket init) ---
@app.get("/api/health")
def health_check():
    """Health check endpoint - returns immediately without blocking on Polymarket."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "polymarket_initialized": _pm_instance is not None
    }

@app.get("/api/test-env")
def test_env():
    """Test environment variables for debugging."""
    import os
    pandascore_key = os.getenv("PANDASCORE_API_KEY")
    return {
        "pandascore_set": bool(pandascore_key),
        "pandascore_length": len(pandascore_key) if pandascore_key else 0,
        "pandascore_preview": pandascore_key[:10] if pandascore_key else None,
        "all_env_keys": [k for k in os.environ.keys() if 'panda' in k.lower()]
    }

@app.get("/")
def root():
    """Root endpoint for Vercel."""
    return {"status": "ok", "message": "Polymarket Agent API"}

# --- Models ---
class AgentToggleRequest(BaseModel):
    agent: str  # "safe", "scalper", "copyTrader"

class DashboardData(BaseModel):
    balance: float
    equity: float
    unrealizedPnl: float
    gasSpent: float
    total_redeemed: float = 0.0
    costs: Dict[str, float] = {}
    riskStatus: Dict[str, Any] # {safe: bool, message: str}
    agents: Dict[str, Dict[str, Any]]
    positions: List[Dict[str, Any]]
    openOrders: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]]
    stats: Dict[str, Any]
    dryRun: bool
    lastUpdate: str
    walletAddress: str  # Bot's wallet address
    maxBetAmount: float = 0.50

# --- Helper Functions ---

# Singleton Polymarket client


def fetch_open_orders_helper() -> List[Dict]:
    """Fetch active orders from CLOB and enrich with market info."""
    pm = get_pm()
    if not pm:
        return []
    
    try:
        orders = pm.get_open_orders()
        enriched = []
        for o in orders:
            # Default structure
            item = {
                "id": o.get("orderID"),
                "token_id": o.get("asset_id") or o.get("token_id"),
                "price": float(o.get("price", 0)),
                "size": float(o.get("size", 0)), # Remaining size
                "side": o.get("side"),
                "market": "Loading..."
            }
            
            # Enrich with Question & Outcome
            try:
                # Fetch market details
                m = pm.get_market(item["token_id"])
                if m:
                    item["market"] = m.question
                    
                    # Try to map token ID to outcome
                    try:
                        import ast
                        # 'clob_token_ids' is usually a string repr of list "['idx1', 'idx2']"
                        tokens = ast.literal_eval(m.clob_token_ids)
                        outcomes = ast.literal_eval(m.outcomes)
                        
                        if item["token_id"] in tokens:
                            idx = tokens.index(item["token_id"])
                            if idx < len(outcomes):
                                item["outcome"] = outcomes[idx]
                    except:
                        item["outcome"] = "Unknown"
            except Exception as e:
                logger.error(f"Failed to enrich order: {e}")
                pass
                
            enriched.append(item)
        return enriched
    except Exception as e:
        logger.error(f"Error fetching open orders: {e}")
        return []

def fetch_positions_helper():
    pm = get_pm()
    if not pm: return []
    try:
        # PM Data API for positions - use DASHBOARD_WALLET for consolidated view
        url = f"https://data-api.polymarket.com/positions?user={DASHBOARD_WALLET}"
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
    pm = get_pm()
    if not pm: return []
    try:
        # Use Activity Endpoint with DASHBOARD_WALLET for consolidated view
        url = f"https://data-api.polymarket.com/activity?user={DASHBOARD_WALLET}&limit={limit}&offset=0"
        import requests
        resp = requests.get(url, timeout=5)
        
        if resp.status_code == 200:
            raw = resp.json()
            trades = []
            for t in raw:
                try:
                    # Filter for TRADE type only
                    if t.get("type") != "TRADE":
                        continue
                        
                    # Parse timestamp (Unix int -> readable string)
                    ts_int = t.get("timestamp")
                    ts_str = str(datetime.fromtimestamp(ts_int)) if ts_int else str(datetime.now())
                    
                    market_title = t.get("title", "N/A")
                    outcome = t.get("outcome", "")
                    
                    # Construct Side (e.g. "Buy No")
                    side = t.get("side", "UNKNOWN")
                    if outcome:
                        side = f"{side} {outcome}"
                        
                    trades.append({
                        "time": ts_str, 
                        "market": market_title,
                        "side": side,
                        "amount": float(t.get("usdcSize", 0)) # Use USD size
                    })
                except Exception as e: 
                    # logger.error(f"Error parsing trade: {e}")
                    continue
            return trades
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
    return []

# --- Endpoints ---

@app.get("/api/dashboard", response_model=DashboardData)
def get_dashboard(background_tasks: BackgroundTasks):
    state = load_state()
    
    # Overlay Supabase state if available
    if HAS_SUPABASE:
        try:
            supa = get_supabase_state()
            state["safe_running"] = supa.is_agent_running("safe")
            state["scalper_running"] = supa.is_agent_running("scalper")
            state["copy_trader_running"] = supa.is_agent_running("copy")
            state["smart_trader_running"] = supa.is_agent_running("smart")
            state["esports_trader_running"] = supa.is_agent_running("esports")
            state["sports_trader_running"] = supa.is_agent_running("sport")
        except Exception as e:
            logger.error(f"Failed to sync dashboard with Supabase: {e}")

    pm = get_pm()
    ctx = get_context()
    
    # 1. Balance - fetch USDC balance for DASHBOARD_WALLET (Proxy) directly
    balance = 0.0
    try:
        import requests
        from web3 import Web3
        # USDC.e contract on Polygon
        USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        # Use public RPC to query balance
        w3 = Web3(Web3.HTTPProvider(os.getenv("POLYGON_RPC", "https://polygon-rpc.com")))
        usdc_abi = '[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]'
        usdc_contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=usdc_abi)
        raw_balance = usdc_contract.functions.balanceOf(Web3.to_checksum_address(DASHBOARD_WALLET)).call()
        balance = raw_balance / 10**6  # USDC has 6 decimals
    except Exception as e:
        logger.error(f"Failed to fetch USDC balance for dashboard wallet: {e}")
        
    # 2. Positions & Equity
    # 2. Positions & Equity
    positions = fetch_positions_helper()
    total_position_value = sum(p['value'] for p in positions)
    unrealized_pnl = sum(p['pnl'] for p in positions)
    # Equity = Cash + Market Value of Positions
    equity = balance + total_position_value
    # Equity usually = Cash + Market Value of Positions
    market_value = sum(p['value'] for p in positions)
    equity = balance + market_value 

    # 3. Trades
    trades = fetch_trades_helper(limit=10) # Minimal for dashboard
    
    # 4. Global Stats
    # We can fetch count from total trades or state
    all_trades = fetch_trades_helper(limit=100)
    trade_count = len(all_trades)
    
    # Calculate Redemptions & Net Volume
    total_redemptions = sum(t['amount'] for t in all_trades if "Redeem" in t.get('side', '') or "Redemption" in t.get('market', ''))
    
    # Volume excludes redemptions to be accurate
    vol_24h = sum(t['amount'] for t in all_trades if "Redeem" not in t.get('side', ''))
    
    # 5. Risk Status
    # Replicate logic: < $3.0 is "Low Balance/Drawdown" warning
    # Or ideally, track drawdowns via state. For now, simple check.
    risk_safe = balance > 3.0
    risk_msg = "No Drawdown Detected" if risk_safe else "Low Balance / Drawdown Limit"
    
    # 6. Gas (Estimated)
    # Polygon fees are low (~$0.01 - $0.05). Let's estimate conservatively based on txn count.
    # We assume roughly 1 txn per trade.
    gas_spent = trade_count * 0.015
    
    # 6b. Costs (Neural & Infra)
    costs = {
        "openai": 0.0,
        "perplexity": 0.0,
        "gemini": 0.0,
        "fly": 0.0,
        "neural_total": 0.0,
        "infra_total": 0.0
    }
    if ctx:
        try:
            costs = ctx.get_financial_metrics()
        except Exception as e:
            logger.error(f"Failed to get financial metrics: {e}")
    
    # 7. Agents - with richer data
    scalper_activity = state.get("scalper_last_activity", "Idle")
    scalper_markets = state.get("scalper_markets", 0)
    scalper_prices = state.get("scalper_prices", {})
    
    # Format scalper activity with live data
    if scalper_markets > 0 and scalper_prices:
        price_summary = ", ".join([f"{k.split('/')[0].upper()}: ${v:,.0f}" if v > 100 else f"{k.split('/')[0].upper()}: ${v:.2f}" 
                                   for k, v in list(scalper_prices.items())[:2]])
        scalper_activity = f"{scalper_activity} | {scalper_markets} markets | {price_summary}"
    
    agents_data = {
        "safe": {
            "running": state.get("safe_running", False),
            "activity": state.get("safe_last_activity", "Idle"),
            "endpoint": state.get("safe_last_endpoint", "Gamma API")
        },
        "scalper": {
            "running": state.get("scalper_running", False),
            "activity": scalper_activity,
            "endpoint": state.get("scalper_last_endpoint", "RTDS WebSocket"),
            "markets": scalper_markets,
            "prices": scalper_prices
        },
        "copyTrader": {
            "running": state.get("copy_trader_running", False),
            "lastSignal": state.get("last_signal", "None"),
            "lastScan": state.get("copy_last_scan", "-")
        },
        "smartTrader": {
            "running": state.get("smart_trader_running", True),
            "activity": state.get("smart_trader_last_activity", "Idle"),
            "positions": state.get("smart_trader_positions", 0),
            "trades": state.get("smart_trader_trades", 0),
            "mode": state.get("smart_trader_mode", "DRY RUN"),
            "lastScan": state.get("smart_trader_last_scan", "-")
        },
        "esportsTrader": {
            "running": state.get("esports_trader_running", True),
            "activity": state.get("esports_trader_last_activity", "Active" if state.get("esports_trader_running") else "Idle"),
            "trades": state.get("esports_trader_trades", 0),
            "mode": state.get("esports_trader_mode", "DRY RUN"),
            "lastScan": state.get("esports_trader_last_scan", datetime.now().strftime("%H:%M:%S")),
            "pnl": state.get("esports_trader_pnl", 0.0),
            "strategy": "Hybrid (Teemu + Strict)"
        },
        "sportsTrader": {
            "running": state.get("sports_trader_running", True),
            "activity": state.get("sports_trader_last_activity", "Active" if state.get("sports_trader_running") else "Idle"),
            "trades": state.get("sports_trader_trades", 0),
            "mode": "DRY RUN" if state.get("dry_run", True) else "LIVE",
            "lastScan": state.get("sports_trader_last_scan", datetime.now().strftime("%H:%M:%S")),
            "strategy": "Direct Gamma (Fast Mode)"
        }
    }

    # Get wallet address - use DASHBOARD_WALLET
    wallet_address = DASHBOARD_WALLET

    # Record snapshot in background
    background_tasks.add_task(record_snapshot, balance, equity, unrealized_pnl)

    # 8. Open Orders
    open_orders = fetch_open_orders_helper()

    return {
        "balance": balance,
        "equity": equity,
        "unrealizedPnl": unrealized_pnl,
        "gasSpent": gas_spent,
        "total_redeemed": total_redemptions,
        "costs": costs,
        "riskStatus": {
            "safe": risk_safe,
            "message": risk_msg
        },
        "agents": agents_data,
        "positions": positions,
        "openOrders": open_orders,
        "trades": trades,
        "stats": {
            "tradeCount": trade_count,
            "volume24h": vol_24h
        },
        "dryRun": state.get("dry_run", True),
        "lastUpdate": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "walletAddress": wallet_address,
        "maxBetAmount": state.get("dynamic_max_bet", 0.50) # Default 0.50 per manual override
    }

@app.post("/api/toggle-agent")
def toggle_agent(req: AgentToggleRequest):
    target = req.agent
    
    # Map frontend names to database names
    agent_map = {
        "safe": "safe",
        "scalper": "scalper",
        "copyTrader": "copy",
        "smartTrader": "smart",
        "esportsTrader": "esports",
        "sportsTrader": "sport"
    }
    db_agent = agent_map.get(target, target)
    
    # Try Supabase first
    if HAS_SUPABASE:
        try:
            supa = get_supabase_state()
            current_state = supa.get_agent_state(db_agent)
            new_running = not current_state.get("is_running", True)
            supa.set_agent_running(db_agent, new_running)
            return {"status": "success", "agent": target, "is_running": new_running, "source": "supabase"}
        except Exception as e:
            logger.error(f"Supabase toggle failed: {e}")
    
    # Fallback to local file
    state = load_state()
    state_key = f"{target.replace('Trader', '_trader')}_running"
    if target == "safe":
        state["safe_running"] = not state.get("safe_running", False)
    elif target == "scalper":
        state["scalper_running"] = not state.get("scalper_running", False)
    elif target == "copyTrader":
        state["copy_trader_running"] = not state.get("copy_trader_running", False)
    elif target == "smartTrader":
        state["smart_trader_running"] = not state.get("smart_trader_running", True)
    elif target == "esportsTrader":
        state["esports_trader_running"] = not state.get("esports_trader_running", True)
    elif target == "sportsTrader":
        state["sports_trader_running"] = not state.get("sports_trader_running", True)
    
    save_state(state)
    return {"status": "success", "state": state, "source": "local"}

class ConfigUpdateRequest(BaseModel):
    key: str
    value: float

@app.post("/api/update-config")
def update_config(req: ConfigUpdateRequest):
    state = load_state()
    # Map friendly keys to state keys
    if req.key == "max_bet":
        state["dynamic_max_bet"] = req.value
    elif req.key == "dry_run":
        # Global Dry Run Toggle
        new_val = bool(req.value)
        state["dry_run"] = new_val
        if HAS_SUPABASE:
            try:
                get_supabase_state().update_agent_state("global", {"is_dry_run": new_val})
            except: pass
    
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
    state["smart_trader_running"] = False
    save_state(state)
    return {"status": "stopped"}


# --- Position Management Endpoints ---

@app.get("/api/positions")
def get_positions():
    """Get all open positions with full details."""
    pm = get_pm()
    if not pm:
        return {"positions": [], "error": "Polymarket client not initialized"}

    try:
        import requests
        address = DASHBOARD_WALLET
        url = f"https://data-api.polymarket.com/positions?user={address}"
        resp = requests.get(url, timeout=10)

        if resp.status_code != 200:
            return {"positions": [], "error": f"API error: {resp.status_code}"}

        raw = resp.json()
        positions = []

        for p in raw:
            try:
                positions.append({
                    "id": p.get("conditionId", p.get("asset", "")),
                    "token_id": p.get("asset", ""),
                    "market": p.get("title", p.get("question", "Unknown")),
                    "side": p.get("outcome", "?"),
                    "size": float(p.get("size", 0)),
                    "cost": float(p.get("cost", 0)),
                    "value": float(p.get("currentValue", p.get("value", 0))),
                    "price": float(p.get("curPrice", 0.5)),
                    "pnl": float(p.get("currentValue", 0)) - float(p.get("cost", 0)),
                    "pnl_pct": ((float(p.get("currentValue", 0)) - float(p.get("cost", 0))) / float(p.get("cost", 1))) * 100 if float(p.get("cost", 0)) > 0 else 0
                })
            except Exception as e:
                logger.error(f"Error parsing position: {e}")
                continue

        return {"positions": positions, "count": len(positions)}

    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        return {"positions": [], "error": str(e)}


@app.get("/api/open-orders")
def get_open_orders():
    """Get all open (pending) orders that haven't been filled yet."""
    pm = get_pm()
    if not pm:
        return {"orders": [], "error": "Polymarket client not initialized"}

    try:
        # Get open orders from CLOB API
        # The py_clob_client has methods to get orders
        orders_data = pm.client.get_orders()

        if not orders_data or not hasattr(orders_data, 'orders'):
            return {"orders": [], "message": "No open orders found"}

        orders = []
        for order in orders_data.orders:
            try:
                # Get market info for the token
                token_id = order.token_id
                market_info = None

                # Try to get market details from token_id
                try:
                    import requests
                    # Extract condition_id from token_id if possible
                    # Token IDs follow pattern: condition_id-outcome_index
                    if '-' in token_id:
                        condition_id = token_id.split('-')[0]
                        market_url = f"https://gamma-api.polymarket.com/markets?condition_id={condition_id}"
                        market_resp = requests.get(market_url, timeout=5)
                        if market_resp.status_code == 200:
                            markets = market_resp.json()
                            if markets:
                                market_info = markets[0]
                except:
                    pass

                order_info = {
                    "id": order.id,
                    "token_id": token_id,
                    "market": market_info.get("question", "Unknown Market") if market_info else "Unknown Market",
                    "side": "BUY" if order.side == 0 else "SELL",
                    "price": float(order.price),
                    "size": float(order.size),
                    "remaining_size": float(order.size) - float(getattr(order, 'size_filled', 0)),
                    "status": "open",
                    "created_at": getattr(order, 'created_at', str(datetime.now())),
                    "outcome": "Unknown"  # Would need additional logic to determine YES/NO
                }
                orders.append(order_info)

            except Exception as e:
                logger.error(f"Error parsing order {getattr(order, 'id', 'unknown')}: {e}")
                continue

        return {"orders": orders, "count": len(orders)}

    except Exception as e:
        logger.error(f"Error fetching open orders: {e}")
        return {"orders": [], "error": str(e)}


class CancelOrderRequest(BaseModel):
    order_id: str


@app.post("/api/cancel-order")
def cancel_order(req: CancelOrderRequest):
    """Cancel a specific open order."""
    pm = get_pm()
    if not pm:
        return {"status": "error", "error": "Polymarket client not initialized"}

    try:
        # Cancel order using CLOB client
        result = pm.client.cancel_order(req.order_id)

        if result.get("success"):
            return {
                "status": "success",
                "message": f"Order {req.order_id} cancelled successfully",
                "order_id": req.order_id
            }
        else:
            return {
                "status": "error",
                "error": result.get("error", "Unknown cancellation error"),
                "order_id": req.order_id
            }

    except Exception as e:
        logger.error(f"Error cancelling order {req.order_id}: {e}")
        return {"status": "error", "error": str(e), "order_id": req.order_id}


@app.post("/api/cancel-all-orders")
def cancel_all_orders():
    """Cancel all open orders."""
    pm = get_pm()
    if not pm:
        return {"status": "error", "error": "Polymarket client not initialized"}

    try:
        # Get all open orders first
        orders_data = pm.client.get_orders()
        if not orders_data or not hasattr(orders_data, 'orders'):
            return {"status": "success", "message": "No open orders to cancel", "cancelled": 0}

        cancelled = 0
        failed = 0
        results = []

        for order in orders_data.orders:
            try:
                order_id = getattr(order, 'id', None)
                if not order_id:
                    continue

                result = pm.client.cancel_order(order_id)
                if result.get("success"):
                    cancelled += 1
                    results.append({"order_id": order_id, "status": "cancelled"})
                else:
                    failed += 1
                    results.append({"order_id": order_id, "status": "failed", "error": result.get("error")})

                import time
                time.sleep(0.5)  # Rate limit

            except Exception as e:
                failed += 1
                results.append({"order_id": getattr(order, 'id', 'unknown'), "status": "error", "error": str(e)})

        return {
            "status": "success",
            "cancelled": cancelled,
            "failed": failed,
            "total": len(orders_data.orders),
            "results": results
        }

    except Exception as e:
        logger.error(f"Error cancelling all orders: {e}")
        return {"status": "error", "error": str(e)}


class ClosePositionRequest(BaseModel):
    token_id: str
    size: float = None  # If None, close entire position
    price: float = None  # If None, use market price


@app.post("/api/close-position")
def close_position(req: ClosePositionRequest):
    """Close a specific position by selling shares."""
    pm = get_pm()
    if not pm:
        return {"status": "error", "error": "Polymarket client not initialized"}
    
    try:
        from py_clob_client.clob_types import OrderArgs
        from py_clob_client.order_builder.constants import SELL
        
        current_value = 0
        
        # Get current position info if size not provided
        if req.size is None or req.price is None:
            import requests
            address = DASHBOARD_WALLET
            url = f"https://data-api.polymarket.com/positions?user={address}"
            resp = requests.get(url, timeout=10)
            
            if resp.status_code == 200:
                for p in resp.json():
                    if p.get("asset") == req.token_id:
                        if req.size is None:
                            req.size = float(p.get("size", 0))
                        if req.price is None:
                            req.price = float(p.get("curPrice", 0.5))
                        current_value = float(p.get("currentValue", 0))
                        break
        
        if not req.size or req.size <= 0:
            return {"status": "error", "error": "No position size found"}
        
        # Check if position is worthless
        if current_value <= 0.01:
            return {
                "status": "worthless",
                "message": "Position is worthless (value ~$0). Nothing to recover.",
                "current_value": current_value
            }
        
        # Get best bid from orderbook for better fill
        sell_price = None
        try:
            orderbook = pm.client.get_order_book(req.token_id)
            if orderbook.bids:
                best_bid = float(orderbook.bids[0].price)
                # Sell slightly below best bid for faster fill
                sell_price = max(0.001, best_bid - 0.01)
            else:
                # No bids = market may be resolved or illiquid
                return {
                    "status": "no_buyers",
                    "message": "No buyers in orderbook. Market may be resolved or illiquid."
                }
        except:
            sell_price = max(0.001, (req.price or 0.5) - 0.05)
        
        # Validate price is in Polymarket's allowed range (0.001 - 0.999)
        sell_price = max(0.001, min(0.999, sell_price))
        
        # Create sell order
        order_args = OrderArgs(
            token_id=str(req.token_id),
            price=sell_price,
            size=req.size,
            side=SELL
        )
        
        signed = pm.client.create_order(order_args)
        result = pm.client.post_order(signed)
        
        if result.get("success") or result.get("status") == "matched":
            return {
                "status": "success",
                "message": f"Sold {req.size:.2f} shares @ ${sell_price:.3f}",
                "size": req.size,
                "price": sell_price,
                "expected_return": req.size * sell_price
            }
        else:
            return {
                "status": "pending",
                "message": f"Order placed at ${sell_price:.3f}. May fill when buyer matches.",
                "order_status": result.get("status")
            }
    
    except Exception as e:
        logger.error(f"Error closing position: {e}")
        return {"status": "error", "error": str(e)}


@app.post("/api/close-all-positions")
def close_all_positions():
    """Close all open positions (skips worthless ones)."""
    pm = get_pm()
    if not pm:
        return {"status": "error", "error": "Polymarket client not initialized"}
    
    try:
        import requests
        from py_clob_client.clob_types import OrderArgs
        from py_clob_client.order_builder.constants import SELL
        
        address = DASHBOARD_WALLET
        url = f"https://data-api.polymarket.com/positions?user={address}"
        resp = requests.get(url, timeout=10)
        
        if resp.status_code != 200:
            return {"status": "error", "error": f"Failed to fetch positions: {resp.status_code}"}
        
        positions = resp.json()
        results = []
        closed = 0
        skipped = 0
        failed = 0
        
        for p in positions:
            try:
                token_id = p.get("asset")
                size = float(p.get("size", 0))
                current_value = float(p.get("currentValue", 0))
                market_title = p.get("title", "")[:40]
                
                if size <= 0:
                    continue
                
                # Skip worthless positions
                if current_value <= 0.01:
                    skipped += 1
                    results.append({
                        "market": market_title,
                        "status": "skipped_worthless",
                        "message": "Position is worthless (~$0)"
                    })
                    continue
                
                # Get best bid from orderbook
                sell_price = None
                try:
                    orderbook = pm.client.get_order_book(token_id)
                    if orderbook.bids:
                        best_bid = float(orderbook.bids[0].price)
                        sell_price = max(0.001, best_bid - 0.01)
                    else:
                        # No bids = can't sell
                        skipped += 1
                        results.append({
                            "market": market_title,
                            "status": "skipped_no_buyers",
                            "message": "No buyers in orderbook"
                        })
                        continue
                except:
                    # Fallback - use curPrice but validate
                    price = float(p.get("curPrice", 0.5))
                    if price <= 0.01:
                        skipped += 1
                        results.append({
                            "market": market_title,
                            "status": "skipped_no_price",
                            "message": "Price too low to sell"
                        })
                        continue
                    sell_price = max(0.001, price - 0.05)
                
                # Validate price is in Polymarket's allowed range
                sell_price = max(0.001, min(0.999, sell_price))
                
                # Sell
                order_args = OrderArgs(
                    token_id=str(token_id),
                    price=sell_price,
                    size=size,
                    side=SELL
                )
                
                signed = pm.client.create_order(order_args)
                result = pm.client.post_order(signed)
                
                if result.get("success") or result.get("status") == "matched":
                    closed += 1
                    results.append({
                        "market": market_title,
                        "status": "closed",
                        "size": round(size, 2),
                        "price": round(sell_price, 3),
                        "expected_return": round(size * sell_price, 2)
                    })
                else:
                    failed += 1
                    results.append({
                        "market": market_title,
                        "status": result.get("status", "unknown")
                    })
                
                import time
                time.sleep(1)  # Rate limit
                
            except Exception as e:
                failed += 1
                results.append({
                    "market": p.get("title", "")[:40],
                    "status": "error",
                    "error": str(e)
                })
        
        return {
            "status": "success",
            "closed": closed,
            "skipped": skipped,
            "failed": failed,
            "total": len(positions),
            "results": results
        }
    
    except Exception as e:
        logger.error(f"Error closing all positions: {e}")
        return {"status": "error", "error": str(e)}


# --- Trade Ledger Endpoints ---

@app.get("/api/ledger")
def get_trade_ledger(limit: int = 100, agent: Optional[str] = None):
    """
    Get comprehensive trade ledger from Supabase.
    Includes all trades, PnL, and costs per agent.
    """
    if not HAS_SUPABASE:
        return {"trades": [], "summary": {}, "error": "Supabase not configured"}
    
    try:
        supa = get_supabase_state()
        trades = supa.get_recent_trades(agent=agent, limit=limit)
        
        # Calculate summary
        summary = {
            "total_trades": len(trades),
            "total_volume": sum(float(t.get("size_usd", 0)) for t in trades),
            "realized_pnl": sum(float(t.get("pnl", 0)) for t in trades if t.get("status") == "closed"),
            "by_agent": {},
            "by_status": {"pending": 0, "filled": 0, "closed": 0, "failed": 0}
        }
        
        for t in trades:
            agent_name = t.get("agent", "unknown")
            if agent_name not in summary["by_agent"]:
                summary["by_agent"][agent_name] = {"trades": 0, "volume": 0, "pnl": 0}
            summary["by_agent"][agent_name]["trades"] += 1
            summary["by_agent"][agent_name]["volume"] += float(t.get("size_usd", 0))
            summary["by_agent"][agent_name]["pnl"] += float(t.get("pnl", 0))
            
            status = t.get("status", "unknown")
            if status in summary["by_status"]:
                summary["by_status"][status] += 1
        
        return {"trades": trades, "summary": summary}
    
    except Exception as e:
        logger.error(f"Error fetching ledger: {e}")
        return {"trades": [], "summary": {}, "error": str(e)}


# --- LLM Activity Endpoints ---



@app.get("/api/context-summary")
def get_context_summary():
    """Get shared context summary (positions, allocation, etc.)."""
    if not get_context:
        return {"error": "Context not available"}
    
    try:
        ctx = get_context()
        return {
            "summary": ctx.get_summary(),
            "positions": ctx.get_open_positions(),
            "recent_trades": ctx.get_recent_trades(20),
            "broadcasts": ctx.get_broadcasts("api", unread_only=False)[-10:]
        }
    except Exception as e:
        logger.error(f"Error fetching context: {e}")
        return {"error": str(e)}


# --- History / Snapshots ---
def record_snapshot(balance, equity, pnl):
    """Record a portfolio snapshot to Supabase (primary) or local JSON (backup)."""
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "balance": balance,
        "equity": equity,
        "unrealized_pnl": pnl
    }
    
    # 1. Try Supabase
    if HAS_SUPABASE:
        try:
            supa = get_supabase_state()
            if hasattr(supa, 'client') and supa.client:
                 supa.client.table("portfolio_snapshots").insert(snapshot).execute()
                 return # Success
        except Exception as e:
            pass

    # 2. Local Fallback
    try:
        history = []
        if os.path.exists(SNAPSHOTS_FILE):
             try:
                 with open(SNAPSHOTS_FILE, 'r') as f:
                     history = json.load(f)
             except json.JSONDecodeError:
                 logger.warning("Snapshot file corrupted. Deleting/Resetting.")
                 try: os.remove(SNAPSHOTS_FILE)
                 except: pass
                 history = []
        
        # Append and prune (keep last 1000)
        history.append(snapshot)
        if len(history) > 1000:
            history = history[-1000:]
            
        with open(SNAPSHOTS_FILE, 'w') as f:
            json.dump(history, f)
    except Exception as e:
        logger.error(f"Failed to save local snapshot: {e}")

@app.get("/api/history")
def get_history(period: str = "24h"):
    """Get portfolio history for graphs."""
    # 1. Try Supabase
    if HAS_SUPABASE:
        try:
            supa = get_supabase_state()
            if hasattr(supa, 'client') and supa.client:
                # Simple query: get last 100 records
                res = supa.client.table("portfolio_snapshots").select("*").order("timestamp", desc=True).limit(100).execute()
                data = res.data
                # Reverse to chronological
                return {"history": data[::-1], "source": "supabase"}
        except: pass

    # 2. Local Fallback
    if os.path.exists(SNAPSHOTS_FILE):
        try:
            with open(SNAPSHOTS_FILE, 'r') as f:
                data = json.load(f)
                return {"history": data, "source": "local"}
        except: pass

    return {"history": [], "source": "empty"}


@app.get("/api/trade-history")
def get_trade_history(limit: int = 50, offset: int = 0):
    """Get complete trade history (fills, redemptions, etc.) like Polymarket portfolio."""
    pm = get_pm()
    if not pm:
        return {"trades": [], "error": "Polymarket client not initialized"}

    try:
        import requests
        address = DASHBOARD_WALLET

        # Get activity (trades) from Data API
        url = f"https://data-api.polymarket.com/activity?user={address}&limit={limit}&offset={offset}"
        resp = requests.get(url, timeout=10)

        if resp.status_code != 200:
            return {"trades": [], "error": f"API error: {resp.status_code}"}

        raw = resp.json()
        trades = []

        for t in raw:
            try:
                # Parse timestamp
                ts_int = t.get("timestamp")
                ts_str = str(datetime.fromtimestamp(ts_int)) if ts_int else str(datetime.now())

                # Determine trade type and details
                trade_type = t.get("type", "UNKNOWN")
                market_title = t.get("title", "Unknown")

                # Handle different trade types
                if trade_type == "TRADE":
                    outcome = t.get("outcome", "")
                    side = t.get("side", "UNKNOWN")

                    # Format side nicely
                    if outcome:
                        side = f"{side} {outcome}"

                    trade_info = {
                        "id": t.get("id", ""),
                        "timestamp": ts_str,
                        "type": "TRADE",
                        "market": market_title,
                        "side": side,
                        "amount": float(t.get("usdcSize", 0)),
                        "price": float(t.get("price", 0)),
                        "fee": float(t.get("fee", 0)),
                        "status": "filled"
                    }

                elif trade_type == "REDEMPTION":
                    trade_info = {
                        "id": t.get("id", ""),
                        "timestamp": ts_str,
                        "type": "REDEMPTION",
                        "market": market_title,
                        "side": "REDEEM",
                        "amount": float(t.get("usdcSize", 0)),
                        "price": 0,
                        "fee": 0,
                        "status": "redeemed"
                    }

                else:
                    # Other activity types
                    trade_info = {
                        "id": t.get("id", ""),
                        "timestamp": ts_str,
                        "type": trade_type,
                        "market": market_title,
                        "side": t.get("description", trade_type),
                        "amount": float(t.get("usdcSize", 0)),
                        "price": 0,
                        "fee": 0,
                        "status": "other"
                    }

                trades.append(trade_info)

            except Exception as e:
                logger.error(f"Error parsing trade: {e}")
                continue

        return {
            "trades": trades,
            "count": len(trades),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error fetching trade history: {e}")
        return {"trades": [], "error": str(e)}


# =============================================================================
# FBP AGENT CHAT
# =============================================================================


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]

# Store conversation history per session (in-memory for now)
chat_sessions: Dict[str, List[Dict[str, str]]] = {}

@app.post("/api/chat")
async def fbp_chat(request: ChatRequest):
    """
    FBP Agent chat endpoint with tool calling.
    """
    try:
        # Ensure we can import from the current directory
        import importlib.util
        fbp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fbp_agent.py")
        spec = importlib.util.spec_from_file_location("fbp_agent", fbp_path)
        fbp_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fbp_module)
        fbp_chat_fn = fbp_module.chat
    except Exception as e:
        logger.error(f"Failed to import FBP Agent: {e}")
        return {
            "response": f"FBP Agent not available - {str(e)}",
            "tool_calls": []
        }
    
    # Convert to dict format
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    
    # Execute chat with tool calling
    result = fbp_chat_fn(messages)
    
    return result


@app.post("/api/chat/{session_id}")
async def fbp_chat_session(session_id: str, request: ChatRequest):
    """
    FBP Agent chat with session history. Persists to Supabase.
    """
    try:
        import importlib.util
        fbp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fbp_agent.py")
        spec = importlib.util.spec_from_file_location("fbp_agent", fbp_path)
        fbp_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fbp_module)
        fbp_chat_fn = fbp_module.chat
    except Exception as e:
        logger.error(f"Failed to import FBP Agent: {e}")
        return {
            "response": f"FBP Agent not available - {str(e)}",
            "tool_calls": []
        }
    
    # Get or create session (in-memory fallback)
    if session_id not in chat_sessions:
        chat_sessions[session_id] = []
    
    # Add new messages to session
    for m in request.messages:
        chat_sessions[session_id].append({"role": m.role, "content": m.content})
        # Persist to Supabase
        if HAS_SUPABASE:
            try:
                supa = get_supabase_state()
                supa.save_chat_message(session_id, m.role, m.content)
            except Exception as e:
                logger.error(f"Failed to save chat message: {e}")
    
    # Execute with full history
    result = fbp_chat_fn(chat_sessions[session_id])
    
    # Store assistant response
    chat_sessions[session_id].append({"role": "assistant", "content": result["response"]})
    
    # Persist assistant response to Supabase
    if HAS_SUPABASE:
        try:
            supa = get_supabase_state()
            supa.save_chat_message(session_id, "assistant", result["response"])
        except Exception as e:
            logger.error(f"Failed to save assistant message: {e}")
    
    return result


@app.delete("/api/chat/{session_id}")
async def clear_chat_session(session_id: str):
    """Clear a chat session."""
    if session_id in chat_sessions:
        del chat_sessions[session_id]
    return {"status": "cleared"}


@app.get("/api/chat/sessions")
async def list_chat_sessions():
    """List all chat sessions from Supabase."""
    if HAS_SUPABASE:
        try:
            supa = get_supabase_state()
            sessions = supa.get_chat_sessions()
            return {"sessions": sessions}
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
    
    # Fallback to in-memory sessions
    return {
        "sessions": [
            {"session_id": sid, "message_count": len(msgs), "last_message": msgs[-1]["content"][:50] if msgs else ""}
            for sid, msgs in chat_sessions.items()
        ]
    }


@app.get("/api/chat/{session_id}/messages")
async def get_chat_messages(session_id: str):
    """Get all messages for a chat session."""
    if HAS_SUPABASE:
        try:
            supa = get_supabase_state()
            messages = supa.get_chat_messages(session_id)
            if messages:
                # Also populate in-memory for FBP to use
                chat_sessions[session_id] = [{"role": m["role"], "content": m["content"]} for m in messages]
                return {"session_id": session_id, "messages": messages}
        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
    
    # Fallback to in-memory
    if session_id in chat_sessions:
        return {"session_id": session_id, "messages": chat_sessions[session_id]}
    
    return {"session_id": session_id, "messages": []}


# --- Auto-Redemption Endpoint ---

@app.post("/api/redeem-positions")
def redeem_positions():
    """
    Automatically redeem all winning positions from resolved markets.
    Converts winning shares to USDC.
    """
    try:
        from agents.utils.auto_redeem import AutoRedeemer
        
        redeemer = AutoRedeemer()
        results = redeemer.scan_and_redeem()
        
        return {
            "status": "success",
            "scanned": results.get("scanned", 0),
            "redeemed": results.get("redeemed", 0),
            "not_resolved": results.get("not_resolved", 0),
            "already_done": results.get("already_redeemed", 0),
            "errors": results.get("errors", 0)
        }
    except ImportError as e:
        return {"status": "error", "error": f"Auto-redeemer not available: {e}"}
    except Exception as e:
        logger.error(f"Redemption error: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/api/llm-activity")
def get_llm_activity_endpoint(limit: int = 50, agent: str = None):
    """Get recent LLM activity logs."""
    if HAS_SUPABASE:
        try:
            supa = get_supabase_state()
            activities = supa.get_llm_activity(limit=limit, agent=agent)
            
            # Simple stats calculation from fetched activities (or placeholder)
            valid_activities = [a for a in activities if a]
            total_cost = sum(a.get("cost_usd", 0) or 0 for a in valid_activities)
            total_tokens = sum(a.get("tokens_used", 0) or 0 for a in valid_activities)
            
            stats = {
                "total_calls": len(activities),
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost,
                "avg_confidence": 0,
                "by_agent": {},
                "decisions": {"BET": 0, "PASS": 0, "ERROR": 0}
            }
            
            return {
                "activities": activities,
                "stats": stats
            }
        except Exception as e:
            logger.error(f"Failed to get LLM activity: {e}")
            return {"activities": [], "stats": {}, "error": str(e)}
    
    return {"activities": [], "stats": {}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
