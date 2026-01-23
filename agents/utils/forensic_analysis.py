import sys
import os
import time
from datetime import datetime
import pandas as pd

# Ensure we can import from parent directories
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from agents.polymarket.polymarket import Polymarket

def analyze_funds():
    print("🔍 INITIALIZING FORENSIC ANALYSIS...")
    pm = Polymarket()
    
    # 1. Get Balance
    balance = pm.get_usdc_balance()
    print(f"💰 CURRENT WALLET BALANCE: ${balance:.2f}")

    # 2. Get Positions (What we are holding)
    print("\n📦 SCANNING HOLDINGS...")
    positions = pm.get_positions()
    portfolio_value = 0.0
    bad_bags = []

    for p in positions:
        size = float(p.get("size", 0))
        if size < 0.1: continue
        
        token_id = p.get("asset")
        market_slug = p.get("market", "Unknown")
        
        # Get current value
        try:
            curr_price = float(pm.client.get_price(token_id))
        except:
            curr_price = 0.0
            
        # We don't have entry price in positions endpoint usually, 
        # so we rely on trade history for that, or if the API returns avgPrice
        # The data-api sometimes returns 'avgPrice' or 'buyPrice'
        entry_price = float(p.get("avgPrice") or p.get("buyPrice") or 0.0) 
        
        val = size * curr_price
        cost = size * entry_price
        pnl = val - cost
        
        portfolio_value += val
        
        print(f"   • {market_slug[:40]}... | Size: {size:.1f} | AvgEntry: ${entry_price:.3f} | Curr: ${curr_price:.3f} | Val: ${val:.2f}")
        
        if entry_price > 0.5 and curr_price < 0.1:
            bad_bags.append({
                "slug": market_slug,
                "loss": pnl,
                "entry": entry_price,
                "curr": curr_price,
                "size": size
            })

    print(f"\n📊 TOTAL PORTFOLIO VALUE (Unrealized): ${portfolio_value:.2f}")

    # 3. Analyze Trade History (The Flow)
    print("\n📜 ANALYZING RECENT TRADES (Last 50)...")
    trades = pm.get_past_trades(limit=50)
    
    total_spend = 0.0
    total_sales = 0.0
    
    # Sort by time
    trades.sort(key=lambda x: int(x.get("timestamp", 0)))
    
    print(f"{'TIME':<20} | {'SIDE':<5} | {'PRICE':<6} | {'SIZE':<8} | {'VALUE':<8} | {'ASSET'}")
    print("-" * 100)
    
    print(f"{'TIME':<20} | {'SIDE':<5} | {'PRICE':<6} | {'SIZE':<8} | {'VALUE':<8} | {'ASSET'}")
    print("-" * 100)
    
    market_cache = {}

    for t in trades:
        # TIMESTAMP FIX
        ts = int(t.get("match_time", t.get("timestamp", 0)))
        dt = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
        
        side = t.get("side")
        price = float(t.get("price", 0))
        size = float(t.get("size", 0))
        value = price * size
        
        # ASSET RESOLUTION
        asset_id = t.get("asset_id")
        asset_name = "Unknown"
        
        if asset_id in market_cache:
             asset_name = market_cache[asset_id]
        else:
             try:
                 mkt = pm.get_market(asset_id)
                 if mkt:
                     # Combine Question + Outcome
                     outcomes = eval(mkt.get("outcomes", "[]")) if isinstance(mkt.get("outcomes"), str) else mkt.get("outcomes")
                     outcome_idx = 0 if t.get("outcome") == "Up" or t.get("outcome") == "Yes" else 1 
                     # This is a guess, let's just use the Question
                     q = mkt.get("question", "Unknown Market")
                     asset_name = f"{q} ({t.get('outcome')})"
                     market_cache[asset_id] = asset_name
             except:
                 pass
        
        # Truncate for display
        asset_display = asset_name[:40]
        
        if side == "BUY":
            total_spend += value
        else:
            total_sales += value
            
        print(f"{dt:<20} | {side:<5} | ${price:<5.3f} | {size:<8.1f} | ${value:<7.2f} | {asset_display}")

    net_flow = total_sales - total_spend
    print("-" * 100)
    print(f"📉 NET FLOW (Last 50 Trades): ${net_flow:.2f}")
    print(f"   • Total Spent: ${total_spend:.2f}")
    print(f"   • Total Sold:  ${total_sales:.2f}")

    if bad_bags:
        print("\n🚨 IDENTIFIED 'WHALE TRAP' LOSSES (Heavy Bags):")
        for bag in bad_bags:
             print(f"   ❌ {bag['slug']}")
             print(f"      Bought @ ${bag['entry']:.2f} -> Now ${bag['curr']:.2f} | Loss: ${bag['loss']:.2f}")

    print("\n🔎 CONCLUSION:")
    print(f"   Wallet: ${balance:.2f}")
    print(f"   Assets: ${portfolio_value:.2f}")
    print(f"   ~Total: ${balance + portfolio_value:.2f}")

if __name__ == "__main__":
    analyze_funds()
