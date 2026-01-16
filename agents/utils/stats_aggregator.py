"""
Stats Aggregator - Combines history from multiple wallet addresses.

This module merges trade history from:
1. Original EOA (Trust Wallet): 0x3C5179f63E580c890950ac7dfCf96e750fB2D046
2. New Proxy Vault (Google): 0xdb1f88Ab5B531911326788C018D397d352B7265c

This ensures accurate PnL calculation across wallet migrations.
"""

import requests
import time
from typing import List, Dict, Any

# Wallet addresses to aggregate
ADDRESSES = {
    "eoa": "0x3C5179f63E580c890950ac7dfCf96e750fB2D046",
    "proxy": "0xdb1f88Ab5B531911326788C018D397d352B7265c"
}

DATA_API_BASE = "https://data-api.polymarket.com"


def fetch_activity_for_address(address: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetches all activity (trades + redemptions) for a given address.
    Handles pagination automatically.
    """
    all_activities = []
    offset = 0
    
    while True:
        url = f"{DATA_API_BASE}/activity?user={address}&limit={limit}&offset={offset}"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            if not data:
                break
            
            # Tag each activity with source wallet
            for act in data:
                act['_source_wallet'] = address
                
            all_activities.extend(data)
            
            if len(data) < limit:
                break
            
            offset += limit
            time.sleep(0.2)  # Rate limit friendly
        except Exception as e:
            print(f"Error fetching activity for {address}: {e}")
            break
    
    return all_activities


def fetch_positions_for_address(address: str) -> List[Dict[str, Any]]:
    """
    Fetches current open positions for an address.
    """
    url = f"{DATA_API_BASE}/positions?user={address}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        positions = resp.json()
        
        for pos in positions:
            pos['_source_wallet'] = address
            
        return positions
    except Exception as e:
        print(f"Error fetching positions for {address}: {e}")
        return []


def get_combined_activity() -> List[Dict[str, Any]]:
    """
    Fetches and merges activity from all tracked addresses.
    Returns a unified, chronologically sorted ledger.
    """
    all_activity = []
    
    for name, address in ADDRESSES.items():
        print(f"Fetching activity for {name} ({address[:8]}...)...")
        activity = fetch_activity_for_address(address)
        all_activity.extend(activity)
        print(f"  Found {len(activity)} transactions.")
    
    # Sort by timestamp descending (most recent first)
    all_activity.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    
    return all_activity


def get_combined_positions() -> List[Dict[str, Any]]:
    """
    Fetches and merges open positions from all tracked addresses.
    """
    all_positions = []
    
    for name, address in ADDRESSES.items():
        positions = fetch_positions_for_address(address)
        all_positions.extend(positions)
    
    return all_positions


def get_total_performance() -> Dict[str, Any]:
    """
    Calculates combined performance metrics across all wallets.
    
    Returns:
        Dict with total_invested, total_proceeds, current_portfolio_value,
        cash_flow, total_pnl, and market_stats breakdown.
    """
    all_activities = get_combined_activity()
    all_positions = get_combined_positions()
    
    market_stats = {}
    total_invested = 0.0
    total_proceeds = 0.0
    
    for act in all_activities:
        act_type = act.get('type')
        side = act.get('side')
        usdc_size = float(act.get('usdcSize', 0) or 0)
        title = act.get('title', 'Unknown Market')
        
        if title not in market_stats:
            market_stats[title] = {"invested": 0.0, "proceeds": 0.0, "net": 0.0}
        
        if act_type == "TRADE":
            if side == "BUY":
                total_invested += usdc_size
                market_stats[title]["invested"] += usdc_size
                market_stats[title]["net"] -= usdc_size
            elif side == "SELL":
                total_proceeds += usdc_size
                market_stats[title]["proceeds"] += usdc_size
                market_stats[title]["net"] += usdc_size
                
        elif act_type == "REDEEM":
            total_proceeds += usdc_size
            market_stats[title]["proceeds"] += usdc_size
            market_stats[title]["net"] += usdc_size
    
    # Add current portfolio value
    current_portfolio_value = 0.0
    for pos in all_positions:
        val = float(pos.get("currentValue", 0) or 0)
        current_portfolio_value += val
        
        title = pos.get('title', pos.get('question', 'Unknown Market'))
        if title in market_stats:
            market_stats[title]["net"] += val
        else:
            market_stats[title] = {"invested": 0.0, "proceeds": 0.0, "net": val}
    
    cash_flow = total_proceeds - total_invested
    total_pnl = cash_flow + current_portfolio_value
    
    return {
        "addresses": ADDRESSES,
        "total_invested": total_invested,
        "total_proceeds": total_proceeds,
        "current_portfolio_value": current_portfolio_value,
        "cash_flow": cash_flow,
        "total_pnl": total_pnl,
        "market_stats": market_stats,
        "activity_count": len(all_activities),
        "position_count": len(all_positions)
    }


if __name__ == "__main__":
    # Test the aggregator
    print("\n" + "="*60)
    print("  📊 Multi-Wallet Stats Aggregator")
    print("="*60 + "\n")
    
    perf = get_total_performance()
    
    print(f"📉 Total Invested:          ${perf['total_invested']:,.2f}")
    print(f"📈 Total Sold/Redeemed:     ${perf['total_proceeds']:,.2f}")
    print(f"💼 Current Portfolio Value: ${perf['current_portfolio_value']:,.2f}")
    print(f"📊 Cash Flow:               ${perf['cash_flow']:,.2f}")
    print("-" * 40)
    
    if perf['total_pnl'] >= 0:
        print(f"✅ TOTAL PnL:               +${perf['total_pnl']:,.2f}")
    else:
        print(f"🔻 TOTAL PnL:               -${abs(perf['total_pnl']):,.2f}")
    
    print(f"\n📋 Activity Count: {perf['activity_count']}")
    print(f"📋 Open Positions: {perf['position_count']}")
