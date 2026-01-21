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
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime
from dotenv import load_dotenv

# Try to import OpenAI for the main chat loop
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

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

# Import Intelligence Layer Components
try:
    from agents.application.smart_context import SmartContext
    from agents.application.hedge_fund_analyst import HedgeFundAnalyst
    from agents.utils.config import load_config, save_config, update_section
    HAS_INTELLIGENCE = True
except ImportError:
    HAS_INTELLIGENCE = False
    SmartContext = None
    HedgeFundAnalyst = None
    load_config = None

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
    },
    "broadcast_command": {
        "description": "Send a direct command to a specific agent (e.g. 'Scan now' to Scalper). Target can be 'all', 'scalper', 'safe', etc.",
        "params": ["message", "target"]
    },
    "get_scalper_metrics": {
        "description": "Get specialized metrics for the Smart Maker-Only Scalper, including instant scalp profits, maker rebates, and compounding velocity.",
        "params": []
    },
    "get_trade_history": {
        "description": "Fetch list of past executed trades.",
        "params": ["limit"]
    },
    "redeem_winnings": {
        "description": "Trigger a scan to redeem winning shares into USDC.",
        "params": []
    },
    # ===== NEW INTELLIGENCE LAYER TOOLS =====
    "get_smart_context": {
        "description": "Get the full 'Smart Context' including wallet health, win/loss streak, market vibes, and liquidity pressure. Use this before making trading decisions.",
        "params": []
    },
    "analyze_trade_opportunity": {
        "description": "Ask the Hedge Fund Analyst AI to analyze a potential trade. Returns APPROVE, REJECT, or REDUCE_SIZE with reasoning and a risk_multiplier (0.0-1.5).",
        "params": ["market_question", "outcome", "proposed_size_usd", "current_price"]
    },
    "manual_override": {
        "description": "Queue a 'Force Trade' command to be picked up by agents. Bypasses risk checks. Use 'action' of FORCE_BUY_YES, FORCE_BUY_NO, or HALT.",
        "params": ["action", "market_id", "amount_usd", "reason"]
    },
    "update_config": {
        "description": "Update an agent's dynamic configuration (e.g., bet_pct, min_confidence, active status). Changes are saved immediately.",
        "params": ["agent_name", "setting_key", "setting_value"]
    },
    # ===== ALPHA RESEARCH TOOLS =====
    "analyze_sentiment": {
        "description": "Deep-dive on a token's social velocity. Compares mentions vs baseline, identifies alpha vs bot accounts, finds skeptic arguments. Returns phase (Accumulation/Euphoria) and recommendation.",
        "params": ["token"]
    },
    "scan_narratives": {
        "description": "Front-run narrative rotations. Scans X for emerging sectors, finds <$10M MC alpha projects, analyzes liquidity environment. Returns 30-day playbook.",
        "params": ["sectors"]
    },
    "build_exit_plan": {
        "description": "Design cold-blooded exit strategy. Defines take-profit levels based on social mania triggers, invalidation points, and DCA-out schedule with moonbag.",
        "params": ["token", "entry_price", "current_price"]
    },
    "rug_check": {
        "description": "Execute anti-rug 'Deception Audit'. Verifies team, checks LP backdoors, analyzes social authenticity. Returns rug_risk_score (1-10) and red flags.",
        "params": ["project"]
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
        if price <= 0: return json.dumps({"error": "Price is 0 or invalid"})
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


def tool_broadcast_command(message: str, target: str) -> str:
    """Broadcast a command to agents via Shared Context."""
    try:
        # Use 'USER' as sender so agents know it's an imperative command
        _get_context().broadcast("USER", message, {"type": "command", "target": target})
        return json.dumps({
            "status": "success",
            "message": f"Command sent to {target}: {message}",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def tool_get_trade_history(limit: int = 20) -> str:
    """Fetch past trades."""
    try:
        trades = _get_pm().get_past_trades(limit=limit)
        # Summarize for chat
        summary = []
        for t in trades:
            summary.append(f"{t.get('side')} {t.get('size')} shares of {t.get('price')} (ID: {t.get('asset_id')})")
        return json.dumps({"trades": summary if summary else trades})
    except Exception as e:
        return json.dumps({"error": str(e)})

def tool_redeem_winnings() -> str:
    """Trigger redemption."""
    try:
        res = _get_pm().redeem_all_winnings()
        return json.dumps(res)
    except Exception as e:
        return json.dumps({"error": str(e)})

def tool_get_scalper_metrics() -> str:
    """Get specialized HFT metrics for the Smart Maker-Only Scalper."""
    try:
        pm = _get_pm()
        # Fetch trades to calculate instant scalp profits (replicates api.py logic)
        trades = pm.get_past_trades(limit=100)
        instant_scalp_profits = sum(t.get('amount', 0) * 0.015 for t in trades if "Sell" in t.get('side', ''))
        
        # Fetch 24h volume for rebate calculation
        try:
            # Try to get 24h volume if available in state or via API
            # For now, we'll try to fetch trade count as velocity proxy too
            with open("bot_state.json", "r") as f:
                state = json.load(f)
            trade_count = state.get("stats", {}).get("tradeCount", len(trades))
            vol_24h = state.get("stats", {}).get("volume24h", 0)
        except:
            trade_count = len(trades)
            vol_24h = 0
            
        estimated_rebate_daily = vol_24h * 0.00035
        
        return json.dumps({
            "instant_scalp_profits": round(instant_scalp_profits, 2),
            "estimated_rebate_daily": round(estimated_rebate_daily, 2),
            "compounding_velocity": trade_count,
            "daily_goal": 248.00,
            "bankroll": 150.00,
            "net_roi": round((instant_scalp_profits / 150.0) * 100, 2)
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

# =============================================================================
# NEW INTELLIGENCE LAYER TOOL IMPLEMENTATIONS
# =============================================================================

def tool_get_smart_context() -> str:
    """Get smart context snapshot."""
    if not HAS_INTELLIGENCE:
        return json.dumps({"error": "Intelligence layer (SmartContext) not available"})
    try:
        ctx = SmartContext()
        snapshot = ctx.get_snapshot()
        return json.dumps(snapshot)
    except Exception as e:
        return json.dumps({"error": str(e)})

def tool_analyze_trade_opportunity(market_question: str, outcome: str, proposed_size_usd: float, current_price: float) -> str:
    """Ask Hedge Fund Analyst."""
    if not HAS_INTELLIGENCE:
        return json.dumps({"error": "Intelligence layer (HedgeFundAnalyst) not available"})
    try:
        analyst = HedgeFundAnalyst()
        decision = analyst.analyze_opportunity(
            market_question=market_question,
            outcome=outcome,
            odds=current_price,
            size_usd=proposed_size_usd
        )
        return json.dumps(decision)
    except Exception as e:
        return json.dumps({"error": str(e)})

def tool_manual_override(action: str, market_id: str, amount_usd: float, reason: str) -> str:
    """Queue a manual command."""
    try:
        # Queue via API is preferred, but here we can write to a file or Context
        payload = {
            "type": "command",
            "target": "all",
            "action": action,
            "market_id": market_id,
            "amount": amount_usd,
            "reason": reason
        }
        _get_context().broadcast("USER_OVERRIDE", f"MANUAL OVERRIDE: {action}", payload)
        return json.dumps({"status": "queued", "message": f"Queued {action} on {market_id}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def tool_update_config(agent_name: str, setting_key: str, setting_value: Any) -> str:
    """Update config."""
    try:
        if not HAS_INTELLIGENCE:
             return json.dumps({"error": "Config management not loaded"})
        
        # Determine value type
        try:
            val = float(setting_value)
            if val.is_integer(): val = int(val)
        except:
            val = setting_value
            if val.lower() == "true": val = True
            elif val.lower() == "false": val = False
            
        new_conf = update_section(agent_name, {setting_key: val})
        return json.dumps({"status": "updated", "new_config": new_conf.get(agent_name, {})})
    except Exception as e:
        return json.dumps({"error": str(e)})

# =============================================================================
# ALPHA RESEARCH TOOL IMPLEMENTATIONS
# =============================================================================

def tool_analyze_sentiment(token: str) -> str:
    """Analyze sentiment velocity for a token."""
    try:
        if not HAS_INTELLIGENCE:
            return json.dumps({"error": "Universal Analyst not available"})
        
        from agents.application.universal_analyst import UniversalAnalyst
        analyst = UniversalAnalyst()
        result = analyst.analyze_sentiment_velocity(token)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})

def tool_scan_narratives(sectors: str) -> str:
    """Scan sector narratives."""
    try:
        if not HAS_INTELLIGENCE:
            return json.dumps({"error": "Universal Analyst not available"})
        
        # Parse sectors list from string if needed
        sector_list = []
        if sectors:
            if isinstance(sectors, list):
                sector_list = sectors
            else:
                sector_list = [s.strip() for s in sectors.split(",")]

        from agents.application.universal_analyst import UniversalAnalyst
        analyst = UniversalAnalyst()
        result = analyst.scan_sector_narratives(sector_list)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})

def tool_build_exit_plan(token: str, entry_price: float, current_price: float) -> str:
    """Build exit strategy."""
    try:
        if not HAS_INTELLIGENCE:
            return json.dumps({"error": "Universal Analyst not available"})
            
        from agents.application.universal_analyst import UniversalAnalyst
        analyst = UniversalAnalyst()
        result = analyst.build_exit_strategy(token, float(entry_price), float(current_price))
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})

def tool_rug_check(project: str) -> str:
    """Execute rug check."""
    try:
        if not HAS_INTELLIGENCE:
            return json.dumps({"error": "Universal Analyst not available"})
            
        from agents.application.universal_analyst import UniversalAnalyst
        analyst = UniversalAnalyst()
        result = analyst.deception_audit(project)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})

# =============================================================================
# FBP AGENT CLASS (CHAT HANDLER)
# =============================================================================

class FBPAgent:
    """
    Stateful interface for the FBP Agent Chat.
    Handles message history and tool execution loop.
    """
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self.history = [
            {"role": "system", "content": """You are FBP Agent (Farzad's Bot), an advanced autonomous trading assistant.
You have access to real-time market data, trading tools, and alpha research capabilities.
Your goal is to help the user manage their portfolio, find opportunities, and execute trades safely.
You are currently optimized for the **Smart Maker-Only HFT Scalper** strategy.

Capabilities:
1. Scalper Insight: Use get_scalper_metrics to get instant scalp profits, pending maker rebates, and cycle velocity. 
   - Instant Scalp Profits come from spread capture (approx 1.5% on fills).
   - Maker Rebates come from volume (approx 0.035%).
   - Daily Target: $248 in total income to reach $10k/month compounding.
   - Bankroll: $150 USDC base.
2. Portfolio Management: Check balances, positions, and Agent status using get_balance, get_positions, get_agents.
3. Market Analysis: Search markets (search_markets), get details (get_market_details), and analyze odds (analyze_market).
4. Trading: Open/close positions (open_trade, close_position). ALWAYS verify market_id and price before trading.
5. Alpha Research: Use New 'Intelligence Layer' tools (analyze_sentiment, scan_narratives) to find edge.
6. Control: You can toggle agents (toggle_agent) and update config (update_config).

Style:
- Be concise, professional, and data-driven.
- When asked for a status report, lead with the Scalper Performance (Income, Rebates, Velocity).
- When suggested a trade, ALWAYS provide a reason and confidence level.
- If a user asks for 'alpha' or 'new tokens', use the scan_narratives tool.
- If a user asks validity of a project, use rug_check.
"""}
        ]
        
        if HAS_OPENAI:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        else:
            self.client = None
            logger.warning("OpenAI client not initialized (missing import or key)")

    def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Process a user message, execute tools, and return response.
        Returns: {
            "response": str,
            "tool_calls": List[Dict]  # For UI display
        }
        """
        if not self.client:
             return {"response": "Error: OpenAI client not available. Check OPENAI_API_KEY.", "tool_calls": []}

        # Add user message
        self.history.append({"role": "user", "content": user_message})
        
        tool_definitions = []
        for name, tool in TOOLS.items():
            tool_definitions.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            p: {"type": "string" if p != "amount_usd" and p != "current_price" else "number"} 
                            for p in tool["params"]
                        },
                        "required": tool["params"]
                    }
                }
            })

        # 1. First LLM Call
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o", # Use high intelligence model
                messages=self.history,
                tools=tool_definitions,
                tool_choice="auto"
            )
            
            msg = response.choices[0].message
            self.history.append(msg)
            
            executed_tools = []
            
            # 2. Handle Tool Calls
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    func_name = tc.function.name
                    args = json.loads(tc.function.arguments)
                    
                    logger.info(f"FBP Tool Call: {func_name}({args})")
                    
                    # Execute
                    result_str = ""
                    try:
                        # Dynamic dispatch
                        tool_func = globals().get(f"tool_{func_name}")
                        if tool_func:
                            # Introspect params to pass correctly
                            # Simple approach: pass kwargs
                            import inspect
                            sig = inspect.signature(tool_func)
                            # call with kwargs that match signature
                            valid_args = {k: v for k, v in args.items() if k in sig.parameters}
                            result_str = tool_func(**valid_args)
                        else:
                            result_str = json.dumps({"error": f"Tool {func_name} not implemented"})
                    except Exception as e:
                        result_str = json.dumps({"error": str(e)})

                    # Record execution for UI
                    executed_tools.append({
                        "tool": func_name,
                        "params": args,
                        "result": json.loads(result_str) if result_str.startswith("{") or result_str.startswith("[") else result_str
                    })
                    
                    # Append result to history
                    self.history.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str
                    })
                
                # 3. Second LLM Call (Interpret results)
                response2 = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=self.history,
                    # No tools needed for final response usually, but keep simple
                )
                final_content = response2.choices[0].message.content
                self.history.append(response2.choices[0].message)
                
                return {
                    "response": final_content,
                    "tool_calls": executed_tools
                }
            
            else:
                return {
                    "response": msg.content,
                    "tool_calls": []
                }
                
        except Exception as e:
            logger.error(f"FBP Chat Error: {e}")
            return {"response": f"I encountered an error: {str(e)}", "tool_calls": []}
