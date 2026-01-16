#!/usr/bin/env python3
"""
Live trading scan - execute real trades on Polymarket
"""

import sys
import os
import time

# Setup paths
sys.path.insert(0, '/Users/farzad/polyagent')

from agents.agents.application.pyml_scalper import CryptoScalper

def live_trading_scan():
    print('🔥 LIVE TRADING SCAN - Finding Real Opportunities...')
    print('=' * 70)

    # Initialize scalper (LIVE MODE - BE CAREFUL!)
    scalper = CryptoScalper(dry_run=False)  # LIVE TRADING MODE

    print('💰 SCALPER INITIALIZED FOR LIVE TRADING')
    print('🔍 Scanning for immediate trade opportunities...')

    # Quick market scan
    markets = scalper.get_available_markets()
    print(f'📊 Found {len(markets)} total markets')

    # Show all markets and their volumes
    print('\n📈 ALL MARKETS FOUND:')
    for i, market in enumerate(markets[:10]):  # Show first 10
        volume = market.get('volume', 0)
        price = market.get('price', 0)
        print(f'  {i+1}. {market.get("question", "Unknown")[:30]}...')
        print(f'     Volume: ${volume:.0f} | Price: ${price:.3f}')

    # Focus on markets with any volume
    active_markets = [m for m in markets if m.get('volume', 0) > 0]
    print(f'\n🎯 {len(active_markets)} markets with >$0 volume')

    if active_markets:
        print('\n🚀 TOP OPPORTUNITIES:')
        for i, market in enumerate(active_markets[:5]):
            price_data = scalper.get_current_price(market['up_token'])
            if price_data and price_data[0] > 0:
                spread = price_data[3] - price_data[1] if price_data[3] and price_data[1] else 0
                print(f'  {i+1}. {market.get("question", "Unknown")[:35]}...')
                print(f'     Price: ${price_data[0]:.3f} | Spread: ${spread:.3f}')
                print(f'     Volume: ${market.get("volume", 0):.0f}')

        print('\n⚡ Starting live scalping session (60 seconds)...')

        # Lower volume threshold for testing
        test_markets = [m for m in active_markets if m.get('volume', 0) > 100]  # >$100 instead of >$1000
        if test_markets:
            print(f'🎯 Testing on {len(test_markets)} markets with >$100 volume')
        else:
            print('🎯 Testing on all active markets (low volume acceptable for demo)')

        # Start the scalping loop
        start_time = time.time()
        trades_executed = 0
        cycles_run = 0

        while time.time() - start_time < 60:  # 60 second test
            try:
                # Run one scalping iteration
                cycles_run += 1
                print(f'🔄 Cycle {cycles_run} running...')
                scalper.run_scalping_cycle()

                # Check if any trades happened
                if hasattr(scalper, 'trades_executed'):
                    if scalper.trades_executed > trades_executed:
                        print(f'💥 TRADE EXECUTED! Total: {scalper.trades_executed}')
                        trades_executed = scalper.trades_executed
                elif hasattr(scalper, 'total_trades'):
                    if scalper.total_trades > trades_executed:
                        print(f'💥 TRADE EXECUTED! Total: {scalper.total_trades}')
                        trades_executed = scalper.total_trades

                time.sleep(3)  # Brief pause between cycles

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f'⚠️ Cycle error: {e}')
                time.sleep(5)

        print(f'\n🏁 Session complete. Cycles run: {cycles_run}')
        print(f'🏁 Trades executed: {getattr(scalper, "trades_executed", getattr(scalper, "total_trades", 0))}')

    else:
        print('\n⚠️ No active markets with sufficient volume found')

    print('\n💡 Live trading scan complete')

if __name__ == "__main__":
    live_trading_scan()