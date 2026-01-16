"""
FBP Agent - Farzad's Polymarket Bot Agent

A conversational AI agent with full context and tool calling capabilities.
Uses Perplexity API with custom tool execution layer.
"""

import os
import re
import json
import logging
import requests
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv

from agents.polymarket.polymarket import Polymarket
from agents.utils.context import get_context
from agents.utils.validator import Validator, SharedConfig
# Robust Supabase Import
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

load_dotenv()
logger = logging.getLogger("FBP")

# Lazy initialization to avoid blocking imports
_pm = None
_config = None
_validator = None
_context = None

def _get_pm():
    global _pm
    if _pm is None:
        _pm = Polymarket()
    return _pm

def _get_config():
    global _config
    if _config is None:
        _config = SharedConfig()
    return _config

def _get_validator():
    global _validator
    if _validator is None:
        _validator = Validator(_get_config(), agent_name="fbp")
    return _validator

def _get_context():
    global _context
    if _context is None:
        _context = get_context()
    return _context

# Backwards compat - these are now lazy
pm = None
config = None
validator = None
context = None


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

TOOLS = {
    "get_balance": {
        "description": "Get current USDC balance and wallet address",
        "params": []
    },
    "get_positions": {
        "description": "Get all open positions with current value and P&L",
        "params": []
    },
    "get_agents": {
        "description": "Get status of all 3 trading agents (safe, scalper, copyTrader)",
        "params": []
    },
    "search_markets": {
        "description": "Search Polymarket for markets by keyword",
        "params": ["query"]
    },
    "get_market_details": {
        "description": "Get detailed info about a specific market including prices and volume",
        "params": ["market_id"]
    },
    "research": {
        "description": "Use web search to research a topic for trading decisions",
        "params": ["topic"]
    },
    "analyze_market": {
        "description": "Analyze a market using LLM to estimate true probability vs market price",
        "params": ["market_question", "current_price"]
    },
    "open_trade": {
        "description": "Open a new position (buy shares)",
        "params": ["market_id", "outcome", "amount_usd"]
    },
    "close_position": {
        "description": "Close/sell an existing position",
        "params": ["market_id"]
    },
    "toggle_agent": {
        "description": "Turn a trading agent on or off. Use agent='dry_run' to switch system mode.",
        "params": ["agent", "enabled"]
    },
    "get_prices": {
        "description": "Get current crypto prices from Binance (BTC, ETH, SOL, XRP)",
        "params": []
    },
    "get_llm_activity": {
        "description": "Get recent LLM decisions and reasoning from all agents",
        "params": ["limit"]
    }
}


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def tool_get_balance() -> str:
    """Get USDC balance from live deployment wallet."""
    try:
        # Use same balance fetching as live deployment dashboard
        import requests
        from web3 import Web3

        # USDC.e contract on Polygon (same as dashboard)
        USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        dashboard_wallet = os.getenv("POLYMARKET_PROXY_ADDRESS", "0xdb1f88Ab5B531911326788C018D397d352B7265c")

        # Use public RPC to query balance (same as dashboard)
        w3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        usdc_abi = '[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]'
        usdc_contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=usdc_abi)
        raw_balance = usdc_contract.functions.balanceOf(Web3.to_checksum_address(dashboard_wallet)).call()
        balance = raw_balance / 10**6  # USDC has 6 decimals

        return json.dumps({
            "balance_usdc": round(balance, 2),
            "wallet": dashboard_wallet[:10] + "..." + dashboard_wallet[-4:]
        })
    except Exception as e:
        # Fallback to Polymarket API if Web3 fails
        try:
            pm = _get_pm()
            balance = pm.get_usdc_balance()
            address = pm.get_address_for_private_key()
            return json.dumps({
                "balance_usdc": round(balance, 2),
                "wallet": address[:10] + "..." + address[-4:]
            })
        except Exception as fallback_e:
            return json.dumps({"error": f"Both methods failed: Web3({e}), Fallback({fallback_e})"})


def tool_get_positions() -> str:
    """Get all open positions from live deployment wallet."""
    try:
        # Use DASHBOARD_WALLET for consolidated view (same as live deployment)
        dashboard_wallet = os.getenv("POLYMARKET_PROXY_ADDRESS", "0xdb1f88Ab5B531911326788C018D397d352B7265c")
        url = f"https://data-api.polymarket.com/positions?user={dashboard_wallet}"
        resp = requests.get(url, timeout=10)
        positions = resp.json()

        result = []
        total_value = 0
        total_pnl = 0

        for p in positions:
            try:
                market = p.get("title", p.get("question", "Unknown"))
                side = p.get("outcome", "?")
                cost = float(p.get("cost", 0))
                val = float(p.get("currentValue", p.get("value", 0)))
                pnl = val - cost
                total_value += val
                total_pnl += pnl

                result.append({
                    "title": market[:50],
                    "outcome": side,
                    "size": round(float(p.get("size", 0)), 2),
                    "value": round(val, 2),
                    "pnl": round(pnl, 2),
                    "market_id": p.get("conditionId", "")[:12]
                })
            except Exception as e:
                logger.warning(f"Error processing position: {e}")
                continue

        return json.dumps({
            "positions": result,
            "total_value": round(total_value, 2),
            "total_pnl": round(total_pnl, 2),
            "count": len(result)
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_get_agents() -> str:
    """Get status of all trading agents from live deployment."""
    try:
        # Try Supabase first (live deployment data)
        if HAS_SUPABASE:
            try:
                supa = get_supabase_state()
                safe_running = supa.is_agent_running("safe")
                scalper_running = supa.is_agent_running("scalper")
                copy_running = supa.is_agent_running("copy")
                smart_running = supa.is_agent_running("smart")
                esports_running = supa.is_agent_running("esports")
                sports_running = supa.is_agent_running("sport")
                dry_run = False  # Live deployment is not dry run
            except Exception as e:
                logger.warning(f"Supabase not available, falling back to local: {e}")
                # Fallback to local file
                with open("bot_state.json", "r") as f:
                    state = json.load(f)
                safe_running = state.get("safe_running", False)
                scalper_running = state.get("scalper_running", False)
                copy_running = state.get("copy_trader_running", False)
                smart_running = state.get("smart_trader_running", False)
                esports_running = state.get("esports_trader_running", False)
                sports_running = state.get("sports_trader_running", False)
                dry_run = state.get("dry_run", True)
        else:
            # Fallback to local file only
            with open("bot_state.json", "r") as f:
                state = json.load(f)
            safe_running = state.get("safe_running", False)
            scalper_running = state.get("scalper_running", False)
            copy_running = state.get("copy_trader_running", False)
            smart_running = state.get("smart_trader_running", False)
            esports_running = state.get("esports_trader_running", False)
            sports_running = state.get("sports_trader_running", False)
            dry_run = state.get("dry_run", True)

        return json.dumps({
            "safe": {
                "running": safe_running,
                "activity": "Active" if safe_running else "Paused"
            },
            "scalper": {
                "running": scalper_running,
                "activity": "HFT Arbitrage" if scalper_running else "Idle"
            },
            "copyTrader": {
                "running": copy_running,
                "activity": "Monitoring whales" if copy_running else "None"
            },
            "smartTrader": {
                "running": smart_running,
                "activity": "Idle" if smart_running else "Off"
            },
            "esportsTrader": {
                "running": esports_running,
                "activity": "Active" if esports_running else "Off"
            },
            "sportsTrader": {
                "running": sports_running,
                "activity": "Active" if sports_running else "Off"
            },
            "dry_run": dry_run
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_search_markets(query: str) -> str:
    """Search for markets."""
    try:
        url = "https://gamma-api.polymarket.com/markets"
        # Fetch more markets to increase hit rate (Gamma search is often fuzzy/limited)
        params = {
            "limit": 50,
            "active": "true",
            "closed": "false"
        }
        resp = requests.get(url, params=params, timeout=10)
        markets = resp.json()
        
        # Filter by query
        query_lower = query.lower()
        matches = []
        
        # 1. Exact/Substring match in filtered list
        for m in markets:
            q = m.get("question", "").lower()
            if query_lower in q:
                try:
                    prices = json.loads(m.get("outcomePrices", "[]")) if m.get("outcomePrices") else []
                    yes_price = float(prices[0]) if prices else 0
                except:
                    yes_price = 0
                
                matches.append({
                    "id": m.get("id", "")[:12],
                    "question": m.get("question", "")[:80],
                    "yes_price": round(yes_price, 3),
                    "volume": m.get("volume", 0)
                })
        
        # 2. If no matches, try generic popular markets
        if not matches:
             matches.append({"note": "No direct matches found. Showing popular markets instead."})
             for m in markets[:5]:
                try:
                    prices = json.loads(m.get("outcomePrices", "[]"))
                    yes_price = float(prices[0]) if prices else 0
                except: yes_price = 0
                matches.append({
                    "id": m.get("id", "")[:12],
                    "question": m.get("question", "")[:80],
                    "yes_price": round(yes_price, 3)
                })

        return json.dumps({
            "markets": matches[:10],
            "count": len(matches)
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_get_market_details(market_id: str) -> str:
    """Get detailed market info."""
    try:
        url = f"https://gamma-api.polymarket.com/markets/{market_id}"
        resp = requests.get(url, timeout=10)
        m = resp.json()
        
        try:
            prices = json.loads(m.get("outcomePrices", "[]")) if m.get("outcomePrices") else []
            yes_price = float(prices[0]) if prices else 0
            no_price = float(prices[1]) if len(prices) > 1 else 1 - yes_price
        except:
            yes_price = 0
            no_price = 0
        
        return json.dumps({
            "question": m.get("question", ""),
            "yes_price": round(yes_price, 3),
            "no_price": round(no_price, 3),
            "volume": m.get("volume", 0),
            "liquidity": m.get("liquidity", 0),
            "end_date": m.get("endDate", ""),
            "condition_id": m.get("conditionId", "")
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_research(topic: str) -> str:
    """Research a topic using Perplexity."""
    try:
        api_key = _get_config().PERPLEXITY_API_KEY
        if not api_key:
            return json.dumps({"error": "No Perplexity API key"})
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "sonar",
            "messages": [
                {"role": "user", "content": f"Research this topic briefly (2-3 sentences): {topic}"}
            ],
            "max_tokens": 300
        }
        
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            json=payload,
            headers=headers,
            timeout=30
        )
        result = resp.json()
        content = result["choices"][0]["message"]["content"]
        
        return json.dumps({"research": content})
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_analyze_market(market_question: str, current_price: float) -> str:
    """Analyze a market using LLM."""
    try:
        is_valid, reason, confidence = _get_validator().validate(
            market_question, "YES", current_price
        )
        
        return json.dumps({
            "recommendation": "BET" if is_valid else "PASS",
            "reason": reason,
            "confidence": round(confidence, 2),
            "market_price": current_price,
            "edge": round((confidence - current_price) * 100, 1) if is_valid else 0
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_open_trade(market_id: str, outcome: str, amount_usd: float) -> str:
    """Open a new trade."""
    try:
        # Get market details first
        url = f"https://gamma-api.polymarket.com/markets/{market_id}"
        resp = requests.get(url, timeout=10)
        market = resp.json()
        
        clob_ids = market.get("clobTokenIds")
        if not clob_ids:
            return json.dumps({"error": "Market has no CLOB tokens"})
        
        tokens = json.loads(clob_ids) if isinstance(clob_ids, str) else clob_ids
        token_id = tokens[0] if outcome.upper() == "YES" else tokens[1]
        
        # Get current price
        prices = json.loads(market.get("outcomePrices", "[]"))
        price = float(prices[0]) if outcome.upper() == "YES" else float(prices[1])
        
        # Calculate size
        size = amount_usd / price
        
        # Place order
        from py_clob_client.clob_types import OrderArgs
        from py_clob_client.order_builder.constants import BUY
        
        pm = _get_pm()
        order_args = OrderArgs(
            token_id=str(token_id),
            price=price,
            size=size,
            side=BUY
        )
        
        signed = pm.client.create_order(order_args)
        result = pm.client.post_order(signed)
        
        if result.get("success") or result.get("status") == "matched":
            return json.dumps({
                "status": "success",
                "market": market.get("question", "")[:50],
                "outcome": outcome,
                "amount": round(amount_usd, 2),
                "price": round(price, 3),
                "shares": round(size, 2)
            })
        else:
            return json.dumps({"error": f"Order failed: {result.get('status', 'unknown')}"})
            
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_close_position(market_id: str) -> str:
    """Close a position by selling shares back to market."""
    try:
        pm = _get_pm()
        # Get current positions
        address = pm.get_address_for_private_key()
        url = f"https://data-api.polymarket.com/positions?user={address}"
        resp = requests.get(url, timeout=10)
        positions = resp.json()
        
        # Find the position
        position = None
        for p in positions:
            if market_id in p.get("conditionId", "") or market_id in p.get("title", ""):
                position = p
                break
        
        if not position:
            return json.dumps({"error": f"Position not found for {market_id}"})
        
        # Get token to sell
        token_id = position.get("asset")
        size = float(position.get("size", 0))
        current_value = float(position.get("currentValue", 0))
        
        # Check if position has any value
        if size <= 0:
            return json.dumps({"error": "No shares to sell", "size": size})
        
        if current_value <= 0.01:
            return json.dumps({
                "status": "worthless",
                "message": "Position is worthless (value ~$0). Nothing to recover.",
                "market": position.get("title", "")[:50],
                "current_value": current_value
            })
        
        # Get best bid from orderbook for accurate pricing
        try:
            orderbook = pm.client.get_order_book(token_id)
            if orderbook.bids:
                best_bid = float(orderbook.bids[0].price)
                # Sell slightly below best bid for faster fill
                sell_price = max(0.01, best_bid - 0.01)
            else:
                # No bids = can't sell
                return json.dumps({
                    "status": "no_buyers",
                    "message": "No buyers in orderbook. Market may be resolved or illiquid.",
                    "market": position.get("title", "")[:50]
                })
        except:
            # Fallback to curPrice but clamp to valid range
            price = float(position.get("curPrice", 0.5))
            sell_price = max(0.01, min(0.99, price - 0.02))
        
        # Validate price is in Polymarket's allowed range (0.001 - 0.999)
        sell_price = max(0.001, min(0.999, sell_price))
        
        # Place sell order
        from py_clob_client.clob_types import OrderArgs
        from py_clob_client.order_builder.constants import SELL
        
        order_args = OrderArgs(
            token_id=str(token_id),
            price=sell_price,
            size=size,
            side=SELL
        )
        
        signed = pm.client.create_order(order_args)
        result = pm.client.post_order(signed)
        
        if result.get("success") or result.get("status") == "matched":
            return json.dumps({
                "status": "success",
                "market": position.get("title", "")[:50],
                "shares_sold": round(size, 2),
                "price": round(sell_price, 3),
                "expected_return": round(size * sell_price, 2)
            })
        else:
            return json.dumps({
                "status": "pending",
                "message": f"Order placed at ${sell_price:.3f}. May fill when buyer matches.",
                "order_status": result.get("status", "unknown")
            })
            
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_toggle_agent(agent: str, enabled: bool) -> str:
    """Toggle an agent on/off."""
    try:
        # Handle Global Dry Run
        if agent.lower() in ["dry_run", "dryrun", "simulation"]:
            # Update local state
            try:
                with open("bot_state.json", "r") as f:
                    state = json.load(f)
                state["dry_run"] = enabled
                with open("bot_state.json", "w") as f:
                    json.dump(state, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to update local state: {e}")

            # Update Supabase
            try:
                supa = get_supabase_state()
                supa.set_global_dry_run(enabled)
            except Exception as e:
                logger.error(f"Failed to update Supabase: {e}")
            
            mode = "DRY RUN (Simulation)" if enabled else "LIVE TRADING (Real Money)"
            return json.dumps({
                "status": "success",
                "mode": mode,
                "message": f"System switched to {mode}"
            })

        with open("bot_state.json", "r") as f:
            state = json.load(f)
        
        key_map = {
            "safe": "safe_running",
            "scalper": "scalper_running",
            "copyTrader": "copy_trader_running"
        }
        
        if agent not in key_map:
            return json.dumps({"error": f"Unknown agent: {agent}"})
        
        state[key_map[agent]] = enabled
        
        with open("bot_state.json", "w") as f:
            json.dump(state, f, indent=2)
        
        return json.dumps({
            "status": "success",
            "agent": agent,
            "enabled": enabled
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_get_prices() -> str:
    """Get current crypto prices from Binance."""
    try:
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
        prices = {}
        
        for symbol in symbols:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            resp = requests.get(url, timeout=5)
            data = resp.json()
            price = float(data.get("price", 0))
            prices[symbol.replace("USDT", "")] = round(price, 2) if price < 1000 else round(price, 0)
        
        return json.dumps(prices)
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_get_llm_activity(limit: int = 10) -> str:
    """Get recent LLM activity."""
    try:
        activities = _get_context().get_llm_activity(limit=limit)
        
        result = []
        for a in activities:
            result.append({
                "agent": a.get("agent"),
                "action": a.get("action_type"),
                "market": a.get("market_question", "")[:40],
                "result": a.get("conclusion"),
                "confidence": a.get("confidence"),
                "time": a.get("timestamp", "")[:19]
            })
        
        return json.dumps({"activities": result})
    except Exception as e:
        return json.dumps({"error": str(e)})


# Tool executor map
TOOL_EXECUTORS = {
    "get_balance": lambda p: tool_get_balance(),
    "get_positions": lambda p: tool_get_positions(),
    "get_agents": lambda p: tool_get_agents(),
    "search_markets": lambda p: tool_search_markets(p.get("query", "")),
    "get_market_details": lambda p: tool_get_market_details(p.get("market_id", "")),
    "research": lambda p: tool_research(p.get("topic", "")),
    "analyze_market": lambda p: tool_analyze_market(p.get("market_question", ""), float(p.get("current_price", 0.5))),
    "open_trade": lambda p: tool_open_trade(p.get("market_id", ""), p.get("outcome", "YES"), float(p.get("amount_usd", 1))),
    "close_position": lambda p: tool_close_position(p.get("market_id", "")),
    "toggle_agent": lambda p: tool_toggle_agent(p.get("agent", ""), p.get("enabled", False)),
    "get_prices": lambda p: tool_get_prices(),
    "get_llm_activity": lambda p: tool_get_llm_activity(int(p.get("limit", 10)))
}


# =============================================================================
# AGENT CHAT
# =============================================================================

def build_system_prompt() -> str:
    """Build the system prompt with current context."""
    
    # Get current state for context
    try:
        balance = _get_pm().get_usdc_balance()
    except:
        balance = 0
    
    # Get agent states
    state = {}
    try:
        with open("bot_state.json", "r") as f:
            state = json.load(f)
        safe_running = state.get("safe_running", False)
        scalper_running = state.get("scalper_running", False)
        copy_running = state.get("copy_trader_running", False)
        dry_run = state.get("dry_run", True)
    except:
        safe_running = scalper_running = copy_running = False
        dry_run = True
        state = {}
    
    tools_desc = "\n".join([
        f"- {name}: {info['description']} | params: {info['params']}"
        for name, info in TOOLS.items()
    ])
    
    return f"""You are FBP (Farzad's Polymarket Bot), an AI assistant for the Polyagent trading system.

## SYSTEM ARCHITECTURE (THE "GANG OF 5")

This is a multi-agent system where 5 autonomous bots work in parallel:

### 1. SAFE AGENT ("The Sniper")
- **Strategy**: Value & Sniper Mode (Limit Orders)
- **Activity**: Scans for >10% edge in Sports/Politics.
- **Unique Feature**: Uses 'Sniper Mode' to place Limit Bids below market price to capture spread.
- **Status**: {"RUNNING" if safe_running else "STOPPED"}

### 2. SCALPER AGENT ("The Grinder")
- **Strategy**: High-Freq Crypto Volatility
- **Activity**: Trades 15-min crypto markets based on Binance momentum.
- **Unique Feature**: Auto-Compounds wins every minute.
- **Status**: {"RUNNING" if scalper_running else "STOPPED"}

### 3. SMART TRADER ("The Brain")
- **Strategy**: Fee-Free Market Analysis
- **Activity**: Trades Politics/Science markets with 0% fees.
- **Unique Feature**: Uses Perplexity/LLM to estimate true odds vs market odds.
- **Status**: {"RUNNING" if state.get("smart_trader_running", True) else "STOPPED"}

### 4. ESPORTS TRADER ("The Teemu")
- **Strategy**: Latency Arbitrage
- **Activity**: Exploits speed differences between bookmakers and Polymarket.
- **Unique Feature**: "Teemu Mode" (High volume scalping).
- **Status**: {"RUNNING" if state.get("esports_trader_running", True) else "STOPPED"}

### 5. COPY TRADER ("The Shadow")
- **Strategy**: Whale Mirroring
- **Activity**: Copies top 1% of profitable wallets.
- **Unique Feature**: Weighted sizing based on whale success rate.
- **Status**: {"RUNNING" if copy_running else "STOPPED"}

## CORE ENGINE: AUTO-COMPOUNDING
All agents follow the "Trade -> Redeem -> Compound" cycle.
- **Redeemer**: A specialized process scans for resolved wins every minute.
- **Compound**: Profits are IMMEDIATELY added to the available balance for the next trade.
- **Goal**: Exponential growth of the account balance.

## CURRENT STATE
- **Balance**: ${balance:.2f} USDC
- **Mode**: {"DRY RUN (simulation)" if dry_run else "LIVE TRADING"}
- **Time**: {datetime.now().strftime("%Y-%m-%d %H:%M")}

## AVAILABLE TOOLS
{tools_desc}

## TOOL CALLING FORMAT
When you need to use a tool, output EXACTLY:
<tool>tool_name</tool>
<params>{{"param1": "value1"}}</params>

Wait for the result before continuing. You can chain multiple tools.

## RESPONSE STYLE
- Be direct, confident, and slightly technical.
- If asked about strategy, refer to the specific agent nicknames (e.g., "The Sniper").
- ALWAYS cite specific numbers (prices, edge %, pnl).
- Confirm actions explicitly (e.g., "I have toggled the Scalper ON").
- Don't give generic advice; give SYSTEM advice.

Let's make money."""


def execute_tool(tool_name: str, params: dict) -> str:
    """Execute a tool and return the result."""
    if tool_name not in TOOL_EXECUTORS:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    
    try:
        result = TOOL_EXECUTORS[tool_name](params)
        logger.info(f"Tool {tool_name}: {result[:100]}...")
        return result
    except Exception as e:
        logger.error(f"Tool {tool_name} error: {e}")
        return json.dumps({"error": str(e)})


def parse_tool_call(text: str) -> Optional[Tuple[str, dict]]:
    """Parse tool call from model output."""
    tool_match = re.search(r"<tool>(\w+)</tool>", text)
    params_match = re.search(r"<params>(\{.*?\})</params>", text, re.DOTALL)
    
    if tool_match:
        tool_name = tool_match.group(1)
        try:
            params = json.loads(params_match.group(1)) if params_match else {}
        except:
            params = {}
        return tool_name, params
    
    return None


def chat(messages: List[Dict[str, str]], max_iterations: int = 5) -> Dict[str, Any]:
    """
    Main chat function with tool execution loop.
    
    Args:
        messages: List of {"role": "user"|"assistant", "content": "..."}
        max_iterations: Max tool calls per turn
        
    Returns:
        {"response": "...", "tool_calls": [...]}
    """
    api_key = _get_config().PERPLEXITY_API_KEY
    if not api_key:
        return {"response": "Error: No Perplexity API key configured", "tool_calls": []}
    
    system_prompt = build_system_prompt()
    tool_calls = []
    
    # Build conversation
    conv_messages = [{"role": "system", "content": system_prompt}]
    conv_messages.extend(messages)
    
    for i in range(max_iterations):
        # Call Perplexity
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "sonar-pro",
            "messages": conv_messages,
            "temperature": 0.3,
            "max_tokens": 1000
        }
        
        try:
            resp = requests.post(
                "https://api.perplexity.ai/chat/completions",
                json=payload,
                headers=headers,
                timeout=60
            )
            result = resp.json()
            assistant_msg = result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Perplexity API error: {e}")
            return {"response": f"API Error: {e}", "tool_calls": tool_calls}
        
        # Check for tool call
        tool_call = parse_tool_call(assistant_msg)
        
        if tool_call:
            tool_name, params = tool_call
            logger.info(f"Executing tool: {tool_name}({params})")
            
            # Execute tool
            tool_result = execute_tool(tool_name, params)
            
            # Record tool call
            tool_calls.append({
                "tool": tool_name,
                "params": params,
                "result": json.loads(tool_result) if tool_result.startswith("{") else tool_result
            })
            
            # Add to conversation and continue
            conv_messages.append({"role": "assistant", "content": assistant_msg})
            conv_messages.append({"role": "user", "content": f"[Tool Result: {tool_result}]"})
        else:
            # No tool call, return final response
            # Clean up any partial tool tags
            clean_response = re.sub(r"<tool>.*?</tool>", "", assistant_msg)
            clean_response = re.sub(r"<params>.*?</params>", "", clean_response, flags=re.DOTALL)
            
            return {
                "response": clean_response.strip(),
                "tool_calls": tool_calls
            }
    
    # Max iterations reached
    return {
        "response": "I've reached the maximum number of tool calls. Here's what I found so far.",
        "tool_calls": tool_calls
    }


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    # Test the agent
    logging.basicConfig(level=logging.INFO)
    
    test_messages = [
        {"role": "user", "content": "What's my balance and positions?"}
    ]
    
    result = chat(test_messages)
    print("\n" + "="*60)
    print("RESPONSE:")
    print(result["response"])
    print("\nTOOL CALLS:")
    for tc in result["tool_calls"]:
        print(f"  - {tc['tool']}: {tc['result']}")
