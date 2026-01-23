
import os
import sys
import time
import requests
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.getcwd())
load_dotenv()

def get_active_markets():
    """Fetch active 15-min crypto markets."""
    url = "https://gamma-api.polymarket.com/markets"
    params = {
        "limit": 1000,
        # "active": "true", # Remove to ensure we see everything
        "closed": "false",
    }
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        markets = resp.json()
        # Filter for "Up or Down" 15-minute markets
        # DEBUG: Print first market to see structure
        if markets:
            print("SAMPLE MARKET DATA:", markets[0])
        
        valid = []
        for m in markets:
            q = m.get("question", "")
            # Keywords for 15-min crypto markets
            if "Up or Down" in q and any(x in q for x in ["Bitcoin", "Ethereum", "Solana", "XRP", "BTC", "ETH", "SOL"]):
                 valid.append(m)
        return valid
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []

def get_order_books(token_ids):
    """Fetch order books for a list of tokens."""
    url = "https://clob.polymarket.com/order-books"
    payload = [
        {"token_id": tid} for tid in token_ids
    ]
    try:
        resp = requests.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching books: {e}")
        return []

def analyze_low_price_volume(books, markets_map):
    """Analyze volume at 1c, 2c, 3c, 4c, 5c."""
    print(f"\n{'='*80}")
    print(f"{'MARKET':<40} | {'1¢ Vol':<10} | {'2¢ Vol':<10} | {'3¢ Vol':<10} | {'4¢ Vol':<10} | {'5¢ Vol':<10}")
    print(f"{'-'*80}")

    total_1c = 0
    total_5c = 0

    for book_data in books:
        token_id = book_data.get("token_id")
        market_name = markets_map.get(token_id, "Unknown")
        
        bids = book_data.get("bids", [])
        
        # Buckets
        vol_1c = sum(float(b['size']) for b in bids if 0.009 <= float(b['price']) <= 0.011)
        vol_2c = sum(float(b['size']) for b in bids if 0.019 <= float(b['price']) <= 0.021)
        vol_3c = sum(float(b['size']) for b in bids if 0.029 <= float(b['price']) <= 0.031)
        vol_4c = sum(float(b['size']) for b in bids if 0.039 <= float(b['price']) <= 0.041)
        vol_5c = sum(float(b['size']) for b in bids if 0.049 <= float(b['price']) <= 0.051)
        
        total_1c += vol_1c
        total_5c += vol_5c

        if vol_1c > 0 or vol_2c > 0 or vol_3c > 0:
            print(f"{market_name[:38]:<40} | {vol_1c:,.0f}      | {vol_2c:,.0f}      | {vol_3c:,.0f}      | {vol_4c:,.0f}      | {vol_5c:,.0f}")

    print(f"{'='*80}")
    print(f"TOTAL 1¢ BID VOLUME: {total_1c:,.0f} shares")
    print(f"TOTAL 5¢ BID VOLUME: {total_5c:,.0f} shares")
    print(f"{'='*80}\n")
    
    if total_1c > 10000:
        print("🤖 ANALYSIS: High bot activity detected at 1¢ floor.")
        print(f"   There are {total_1c:,.0f} shares ($ {total_1c * 0.01:,.2f}) waiting to buy at 1¢.")
    else:
        print("🟢 ANALYSIS: Low competition at 1¢. Easier to get fills.")

def main():
    print("🔍 Scanning 15-minute Crypto Markets for Bot Walls...")
    markets = get_active_markets()
    print(f"   Found {len(markets)} active markets.")
    
    token_ids = []
    markets_map = {}
    
    for m in markets:
        # Check both outcomes
        upt = m["clobTokenIds"][0]
        dwt = m["clobTokenIds"][1]
        token_ids.extend([upt, dwt])
        markets_map[upt] = f"{m['question']} (UP)"
        markets_map[dwt] = f"{m['question']} (DOWN)"
    
    if token_ids:
        books = get_order_books(token_ids)
        analyze_low_price_volume(books, markets_map)
    else:
        print("No tokens found.")

if __name__ == "__main__":
    main()
