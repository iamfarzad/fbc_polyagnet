import os
import sys
import requests
import time
from dotenv import load_dotenv

# Setup path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../.."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "agents"))

try:
    from agents.agents.polymarket.polymarket import Polymarket
except ImportError:
    try:
        from agents.polymarket.polymarket import Polymarket
    except ImportError:
         print("Failed to import Polymarket")
         sys.exit(1)

def main():
    load_dotenv()
    
    poly = Polymarket()
    address = poly.get_address_for_private_key()
    
    print("\n---------------------------------------------------")
    print("         📊  PnL Analysis (Realized + Unrealized)   ")
    print(f"         Address: {address}")
    print("---------------------------------------------------\n")
    
    # ---------------------------------------------------------
    # 1. Fetch ALL Activity (Trades + Redemptions)
    # ---------------------------------------------------------
    all_activities = []
    limit = 100
    offset = 0
    
    print("Fetching full history from Data API...")
    
    while True:
        url = f"https://data-api.polymarket.com/activity?user={address}&limit={limit}&offset={offset}"
        try:
            resp = requests.get(url)
            data = resp.json()
            if not data:
                break
            
            all_activities.extend(data)
            
            if len(data) < limit:
                break
            
            offset += limit
            time.sleep(0.2) # Rate limit friendly
        except Exception as e:
            print(f"Error fetching activity: {e}")
            break
            
    # ---------------------------------------------------------
    # 2. Calculate Realized PnL (from historical flows)
    # ---------------------------------------------------------
    
    # Group by Market Title for detailed stats
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
            # Redemptions are proceeds
            total_proceeds += usdc_size
            market_stats[title]["proceeds"] += usdc_size
            market_stats[title]["net"] += usdc_size

    # ---------------------------------------------------------
    # 3. Fetch Open Positions (Unrealized Value)
    # ---------------------------------------------------------
    positions_url = f"https://data-api.polymarket.com/positions?user={address}"
    current_portfolio_value = 0.0
    open_positions_count = 0
    
    try:
        p_resp = requests.get(positions_url)
        positions = p_resp.json()
        
        for p in positions:
            val = float(p.get("currentValue", 0) or 0)
            current_portfolio_value += val
            open_positions_count += 1
            
            # Adjust market net calculation:
            # Net PnL = (Proceeds + Redemption + CurrentValue) - Invested
            # So we add CurrentValue to the 'net' tracker for that market
            title = p.get('title', p.get('question', 'Unknown Market'))
            if title in market_stats:
                market_stats[title]["net"] += val
            else:
                # Might be a market we bought but activity API missed? Or transferred in?
                # Assume invested 0 if not found in activity (should not happen usually)
                market_stats[title] = {"invested": 0.0, "proceeds": 0.0, "net": val}
                
    except Exception as e:
        print(f"Error fetching positions: {e}")

    # ---------------------------------------------------------
    # 4. Final Calculations
    # ---------------------------------------------------------
    
    # Cash PnL (Realized mostly, defines cash flow state)
    cash_flow = total_proceeds - total_invested
    
    # Total PnL = (Cash In/Out Net) + Portfolio Value
    # Basically: (Sells + Redemptions) - Buys + CurrentHoldings
    total_pnl = cash_flow + current_portfolio_value
    
    # Get Balance
    try:
        balance = poly.get_usdc_balance()
    except:
        balance = 0.0

    total_account_value = balance + current_portfolio_value

    # ---------------------------------------------------------
    # 5. Output
    # ---------------------------------------------------------
    print(f"📉 Total Bought (Cost):      ${total_invested:,.2f}")
    print(f"📈 Total Sold/Redeemed:      ${total_proceeds:,.2f}")
    print(f"💼 Current Portfolio Value:  ${current_portfolio_value:,.2f}")
    print(f"💰 Current Cash Balance:     ${balance:,.2f}")
    print(f"🏦 Total Account Value:      ${total_account_value:,.2f}")
    print("---------------------------------------------------")
    
    if total_pnl >= 0:
        print(f"✅ TOTAL PnL:               +${total_pnl:,.2f}")
    else:
        print(f"🔻 TOTAL PnL:               -${abs(total_pnl):,.2f}")
    
    print("\n---------------------------------------------------")
    print("         🏆 Top Performers (By Net PnL)            ")
    print("---------------------------------------------------")
    
    # Sort by Net PnL
    sorted_markets = sorted(market_stats.items(), key=lambda x: x[1]['net'], reverse=True)
    
    # Show Top 5
    for m_title, stats in sorted_markets[:5]:
        net = stats['net']
        if net > 0.01: # Filter tiny dust
            print(f"✅ +${net:,.2f} | {m_title[:60]}...")
            
    print("\n---------------------------------------------------")
    print("         💀 Worst Performers                       ")
    print("---------------------------------------------------")
    
    # Show Bottom 5
    for m_title, stats in sorted_markets[-5:]:
        net = stats['net']
        if net < -0.01: # Filter tiny dust
            print(f"🔻 -${abs(net):,.2f} | {m_title[:60]}...")
            
    print("\n")

if __name__ == "__main__":
    main()
