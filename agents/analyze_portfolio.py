
import os
import sys
import time
import requests
from dotenv import load_dotenv

# Add current dir to path to find 'agents' package if needed
sys.path.append(os.getcwd())

try:
    from agents.polymarket.polymarket import Polymarket
except ImportError:
    # Try adding parent directory
    sys.path.append(os.path.dirname(os.getcwd()))
    from agents.polymarket.polymarket import Polymarket

load_dotenv()

def analyze_portfolio():
    print("Initializing Polymarket client...")
    try:
        pm = Polymarket()
        address = pm.get_address_for_private_key()
        print(f"Stats for Address: {address}")
    except Exception as e:
        print(f"Error initializing: {e}")
        return

    addresses = [address]
    
    # Potential old wallet from git history
    old_wallet = "0xdb1f88Ab5B531911326788C018D397d352B7265c"
    addresses.append(old_wallet)
    
    # Check for Proxy Wallet (Funder)
    funder = os.getenv("POLYMARKET_FUNDER")
    if funder and funder.lower() != address.lower():
        print(f"Funds located in Proxy: {funder}")
        addresses.append(funder)
        
    all_positions = []
    
    for addr in addresses:
        print(f"Fetching positions for {addr}...")
        url = f"https://data-api.polymarket.com/positions?user={addr}"
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                pos = resp.json()
                if pos:
                    print(f"  Found {len(pos)} raw records.")
                    all_positions.extend(pos)
        except Exception as e:
            print(f"  Error: {e}")

    # Deduplicate by asset if needed (unlikely to have same asset in both usually, but safe to keep list)
    
    # Filter active positions
    active_positions = []
    total_invested = 0
    total_value = 0
    
    # Relaxed filter and debug print
    print("\nProcessing positions...")
    for p in all_positions:
        size = float(p.get("size", 0))
        asset = p.get("asset", "")
        
        # Keep everything > 0 basically
        if size > 0.000001: 
            active_positions.append(p)
        else:
            # Check if it has non-zero value despite small size? Unlikely.
            pass

    if not active_positions:
        print("No active positions found (after proxy check).")
    else:
        print(f"\nFound {len(active_positions)} active positions. Analyzing details...")
        print("-" * 140)
        print(f"{'Question':<50} | {'Side':<5} | {'Size':<8} | {'Entry':<6} | {'Curr':<6} | {'Value':<8} | {'PnL $':<8} | {'PnL %':<6} | {'Status':<10}")
        print("-" * 140)

        for p in active_positions:
            token_id = p.get("asset")
            size = float(p.get("size"))
            avg_price = float(p.get("avgBuyPrice", 0))
            
            # Get market details via direct Gamma Call
            try:
                gamma_url = "https://gamma-api.polymarket.com/markets"
                resp = requests.get(gamma_url, params={"clob_token_ids": token_id}, timeout=5)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data and isinstance(data, list):
                        market = data[0]
                        question = market.get("question", "Unknown")[:48]
                        
                        outcomes = eval(market.get("outcomes", "['Yes', 'No']")) if isinstance(market.get("outcomes"), str) else market.get("outcomes", ["Yes", "No"])
                        token_ids = market.get("clobTokenIds", [])
                        
                        side = "?"
                        if token_id in token_ids:
                            idx = token_ids.index(token_id)
                            if idx < len(outcomes):
                                side = outcomes[idx]
                        
                        # Get prices
                        outcome_prices = eval(market.get("outcomePrices", "['0', '0']")) if isinstance(market.get("outcomePrices"), str) else market.get("outcomePrices", ["0", "0"])
                        current_price = 0.0
                        if token_id in token_ids:
                            idx = token_ids.index(token_id)
                            if idx < len(outcome_prices):
                                current_price = float(outcome_prices[idx])
                                
                        # Calc metrics
                        cost_basis = size * avg_price
                        curr_value = size * current_price
                        pnl = curr_value - cost_basis
                        pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
                        
                        total_invested += cost_basis
                        total_value += curr_value
                        
                        pnl_str = f"${pnl:+.2f}"
                        
                        # Status check
                        status = "OPEN"
                        if market.get("closed"): status = "CLOSED"
                        if market.get("active") == False: status = "INACTIVE"
                        
                        print(f"{question:<50} | {side:<5} | {size:<8.1f} | ${avg_price:<5.3f} | ${current_price:<5.3f} | ${curr_value:<7.2f} | {pnl_str:<8} | {pnl_pct:<6.1f}% | {status:<10}")
                    else:
                        print(f"Market not found for asset {token_id}")
                else:
                    print(f"API Error fetching market for {token_id}")
                
            except Exception as e:
                print(f"Error analyzing position {token_id}: {e}")
                import traceback
                traceback.print_exc()

        print("-" * 140)
        total_pnl = total_value - total_invested
        total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0
        
        print(f"TOTAL INVESTED: ${total_invested:.2f}")
        print(f"TOTAL VALUE:    ${total_value:.2f}")
        print(f"TOTAL PnL:      ${total_pnl:+.2f} ({total_pnl_pct:+.2f}%)")
    
    # Check balance
    balance = pm.get_usdc_balance()
    print(f"CASH BALANCE:   ${balance:.2f}")
    print(f"TOTAL EQUITY:   ${(balance + total_value):.2f}")

    # Fetch Trade History
    print("\nFetching recent trade activity...")
    # Try different endpoints for history
    trades = []
    try:
        # trades endpoint often takes maker_address or taker_address
        # We'll try fetching trades where we were the maker (common for limit orders) or taker
        url_trades = f"https://data-api.polymarket.com/trades?maker_address={address}&limit=50"
        resp = requests.get(url_trades, timeout=10)
        if resp.status_code == 200:
             trades.extend(resp.json())
        
        url_trades_taker = f"https://data-api.polymarket.com/trades?taker_address={address}&limit=50"
        resp = requests.get(url_trades_taker, timeout=10)
        if resp.status_code == 200:
             trades.extend(resp.json())
             
        # Sort by timestamp descending
        trades.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        trades = trades[:20] # Show last 20

        # INFER PROXY ADDRESS from trades
        # If we found trades using the EOA as signer, the maker_address might be the proxy
        if trades:
            potential_proxy = trades[0].get("maker_address")
            if potential_proxy and potential_proxy.lower() not in [a.lower() for a in addresses]:
                print(f"\n[!] Discovered potential Proxy Address from trades: {potential_proxy}")
                print(f"    Fetching positions for inferred proxy...")
                addresses.append(potential_proxy)
                
                # Fetch positions for this new address
                url = f"https://data-api.polymarket.com/positions?user={potential_proxy}"
                try:
                    resp = requests.get(url, timeout=15)
                    if resp.status_code == 200:
                        pos = resp.json()
                        if pos:
                            print(f"    Found {len(pos)} raw records for proxy.")
                            all_positions.extend(pos)
                except Exception as e:
                    print(f"    Error: {e}")

    except Exception as e:
        print(f"Error fetching trades: {e}")

    # Re-process active positions with new data
    active_positions = []
    print("\nRe-processing positions with inferred proxy data...")
    for p in all_positions:
        size = float(p.get("size", 0))
        if size > 0.000001: 
            active_positions.append(p)
        print("-" * 120)
        print(f"{'Time':<20} | {'Side':<4} | {'Size':<8} | {'Price':<6} | {'Asset':<30} | {'Tx Hash':<20}")
        print("-" * 120)
        
        for t in trades:
            try:
                # Parse timestamp
                ts = int(t.get("timestamp", 0))
                # Convert to readable (check if ms or s)
                if ts > 10000000000: # ms
                    ts = ts / 1000
                import datetime
                time_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
                
                side = t.get("side", "?")
                size = float(t.get("size", 0))
                price = float(t.get("price", 0))
                asset = t.get("asset", "")[:28]
                tx = t.get("transactionHash", "")[:18] + "..."
                
                print(f"{time_str:<20} | {side:<4} | {size:<8.1f} | ${price:<5.3f} | {asset:<30} | {tx:<20}")
            except:
                pass
        
        # Resolve Asset IDs for top trades
        print("\nResolving Asset Details...")
        print("-" * 120)
        seen_assets = set(t.get("asset") for t in trades if t.get("asset"))
        gamma_url = "https://gamma-api.polymarket.com/markets"
        
        for asset_id in seen_assets:
            try:
                # Shorten ID for display
                short_id = asset_id[:15] + "..."
                
                # Direct Gamma Call to avoid wrapper overwriting logic
                resp = requests.get(gamma_url, params={"clob_token_ids": asset_id}, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data and isinstance(data, list):
                        market = data[0]
                        question = market.get("question", "Unknown")
                        outcomes = eval(market.get("outcomes", "['Yes', 'No']")) if isinstance(market.get("outcomes"), str) else market.get("outcomes", ["Yes", "No"])
                        
                        # Raw clobTokenIds is a list in the JSON
                        token_ids = market.get("clobTokenIds", [])
                        
                        side = "?"
                        if asset_id in token_ids:
                            idx = token_ids.index(asset_id)
                            if idx < len(outcomes):
                                side = outcomes[idx]
                        
                        print(f"Asset {short_id}: [{side}] {question}")
                    else:
                        print(f"Asset {short_id}: Market not found")
                else:
                    print(f"Asset {short_id}: API Error {resp.status_code}")
                
                time.sleep(0.3) # Rate limit
                
            except Exception as e:
                print(f"Error resolving {short_id}: {e}")
                time.sleep(0.5)

        print("-" * 120)

if __name__ == "__main__":
    analyze_portfolio()
