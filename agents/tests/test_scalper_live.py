
import sys
import os
import json
import logging
import time
import requests
from collections import deque

# Add agents directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestScalper")

from agents.application.pyml_scalper import CryptoScalper

def test_pipeline():
    print("\n" + "="*60)
    print("🚀 DIAGNOSTIC MODE: Crypto Scalper Pipeline")
    print("="*60)
    
    trader = CryptoScalper(dry_run=True)
    
    # 1. Test Polymarket Fetch
    print("\n🛒 Step 1: Testing Polymarket 15-min Market Fetch...")
    try:
        markets = trader.get_available_markets()
        print(f"   Success! Found {len(markets)} active 'Up or Down' markets.")
        
        if markets:
            print("\n   --- Top 5 Markets Scanned ---")
            for m in markets[:5]:
                q = m.get("question", "")
                print(f"   - {q[:60]}...")
                # Fetch price
                clob_ids = json.loads(m.get("clobTokenIds")) if isinstance(m.get("clobTokenIds"), str) else m.get("clobTokenIds")
                token_id = clob_ids[0] # YES token
                try:
                    mid, bid, ask = trader.get_current_price(token_id)
                    print(f"     Price: {mid:.3f} (Bid: {bid:.3f}, Ask: {ask:.3f})")
                except Exception as e:
                    print(f"     ⚠️ Price fetch failed: {e}")
                    continue
                
                # Run safeguards
                safe, reasons = trader.run_all_safeguards(market=m, token_id=token_id, entry_price=bid)
                status = "✅ SAFE" if safe else f"❌ UNSAFE: {', '.join(reasons)}"
                print(f"     Status: {status}")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")

    # 2. Test Binance WebSocket
    print("\n⚡ Step 2: Testing Binance WebSocket Connections...")
    print("   Connecting to Binance stream (waiting 5s for data)...")
    
    # Manually trigger connection logic if not auto-started
    if not trader.binance_connected:
        import threading
        # Check if verify_binance_ws or run_binance_ws exists
        target_method = getattr(trader, "run_binance_ws", getattr(trader, "start_binance_ws", None))
        if target_method:
             t = threading.Thread(target=target_method)
             t.daemon = True
             t.start()
        else:
             print("   ❌ Error: Could not find Binance WS method")
        
    time.sleep(5)
    
    connected_symbols = 0
    for symbol, prices in trader.binance_history.items():
        count = len(prices)
        if count > 0:
            last_price = prices[-1][1]
            connected_symbols += 1
            print(f"   ✅ {symbol.upper()}: {count} updates. Last: ${last_price:.2f}")
        else:
            print(f"   ⚠️ {symbol.upper()}: No data received.")

    # 3. Test Momentum Algo
    print("\n📈 Step 3: Testing Momentum Calculation...")
    for symbol in ["btcusdt", "ethusdt", "solusdt", "xrpusdt"]:
        # Mock some data if empty
        if len(trader.binance_history[symbol]) < 2:
            trader.binance_history[symbol].append((time.time() - 10, 100.0))
            trader.binance_history[symbol].append((time.time(), 100.05)) # +0.05%
            
        momentum = trader.calculate_binance_momentum(symbol)
        print(f"   {symbol.upper()} Momentum: {momentum*100:+.4f}% (Threshold: {trader.current_threshold*100:.3f}%)")
        
        if abs(momentum) > trader.current_threshold:
            print(f"      🔥 SIGNAL TRIGGERED!")
        else:
            print(f"      ⏳ No signal.")

if __name__ == "__main__":
    test_pipeline()
