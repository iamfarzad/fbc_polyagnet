"""
BACKTRACK TRADES
Fetches full trade history for a wallet to reconstruct the portfolio timeline.

Usage:
    python agents/scripts/python/backtrack_trades.py
"""

import requests
import datetime
from collections import defaultdict

# WALLET TO ANALYZE (Proxy)
TARGET_WALLET = "0xdb1f88Ab5B531911326788C018D397d352B7265c"
ADDITIONAL_WALLETS = ["0x3C5179f63E580c890950ac7dfCf96e750fB2D046"]

def fetch_trades(wallet):
    print(f"📡 Fetching fills for {wallet[:10]}...")
    trades = []
    cursor = ""
    
    while True:
        url = f"https://data-api.polymarket.com/trades?maker_address={wallet}&limit=100&after={cursor}"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if not data: break
            
            chunk = [t for t in data if t.get("maker_address", "").lower() == wallet.lower() or t.get("taker_address", "").lower() == wallet.lower()]
            trades.extend(chunk)
            
            if len(data) < 100: break
            cursor = data[-1].get("timestamp", "")
            if not cursor: break
        except Exception as e:
            print(f"❌ Error: {e}")
            break
            
    print(f"   Has {len(trades)} trades.")
    return trades

def analyze_timeline(trades):
    # Sort by time asc
    trades.sort(key=lambda x: x.get("timestamp", 0))
    
    total_spend = 0
    total_return = 0
    net_pnl = 0
    
    print(f"\n📅 TRADE HISTORY (Oldest to Newest)")
    print(f"{'DATE':<20} | {'SIDE':<5} | {'MARKET':<40} | {'SIZE':<10} | {'PRICE':<6} | {'VALUE':<10}")
    print("-" * 110)
    
    for t in trades:
        ts = int(t.get("timestamp", 0))
        date = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
        
        side = t.get("side", "UNK")
        size = float(t.get("size", 0))
        price = float(t.get("price", 0))
        value = size * price
        
        # Determine if Buy or Sell based on maker/taker/side logic isn't perfect in API 
        # but broadly: 'BUY' side usually means spending USDC.
        
        market_name = "Unknown Market" 
        # (We'd need to resolve asset_id to name, but for speed just showing basic data)
        
        print(f"{date:<20} | {side:<5} | {t.get('asset', 'Unknown Asset')[:10]}... | {size:<10.2f} | {price:<6.3f} | ${value:<10.2f}")
        
    print(f"\n📊 SUMMARY for {TARGET_WALLET[:10]}...")
    print(f"   Total Trades: {len(trades)}")
    # Note: Accurate PnL requires complex asset resolution.

if __name__ == "__main__":
    trades = fetch_trades(TARGET_WALLET)
    analyze_timeline(trades)
