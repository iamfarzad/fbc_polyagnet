import os
import sys

# Set path to project root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.insert(0, PROJECT_ROOT)

from agents.application.pyml_scalper import CryptoScalper

def analyze_walls():
    # Init Scalper in Dry Run to get access to its connectors
    # Set dry_run=True to avoid trading, just scanning
    bot = CryptoScalper(dry_run=True)
    
    print("SEARCHING FOR ACTIVE MARKETS VIA SCALPER LOGIC...")
    markets = bot.get_available_markets()
    
    # Check if any markets were found
    if not markets:
        print("No active markets found by scalper.")
        return

    # Analyze the first one found
    market = markets[0]
    if isinstance(market, dict):
        # Try both camelCase and snake_case
        token_id_raw = market.get('clob_token_ids') or market.get('clobTokenIds') 
        if not token_id_raw:
             # Fallback to up_token / down_token directly
             token_id_raw = market.get('up_token') # Default to UP token
    else:
        # It might be a SimpleMarket object
        token_id_raw = getattr(market, 'clob_token_ids', [])
        if not token_id_raw:
             token_id_raw = getattr(market, 'up_token', None)
        
    print(f"Raw Token ID: {token_id_raw}")
    
    import ast
    token_id = token_id_raw
    if isinstance(token_id_raw, str):
        try:
             # It might be a string representation of a list "['0x...']"
            parsed = ast.literal_eval(token_id_raw)
            if isinstance(parsed, list) and len(parsed) > 0:
                token_id = parsed[0]
            else:
                 token_id = str(token_id_raw)
        except:
             pass 
    elif isinstance(token_id_raw, list):
        if len(token_id_raw) > 0:
            token_id = token_id_raw[0]
        else:
            print("Empty token ID list")
            return

    if not token_id:
        print("Could not determine Token ID from market data.")
        return

    print(f"Target Token ID: {token_id}")

    asset = getattr(market, 'question', 'Unknown') if not isinstance(market, dict) else market.get('question')

    print(f"\nAnalyzing Order Book: {asset}")
    print(f"Token ID: {token_id}")
    print("-" * 50)
    
    # Use bot's internal Polymarket client to get order book
    book = bot.pm.get_orderbook(token_id)
    
    print(f"BIDS (Buyers - Competitors trying to buy cheap):")
    if hasattr(book, 'bids') and book.bids:
        # Sort desc by price
        bids = sorted(book.bids, key=lambda x: float(x.price), reverse=True)[:10]
        for b in bids:
            price = float(b.price)
            size = float(b.size)
            print(f"   ${price:.2f} | Size: {size:.2f} shares {'🚨 WALL' if size > 1000 else ''}")
    else:
        print("   (Empty Bid Side)")

    print("-" * 20)
    print(f"ASKS (Sellers - Competitors trying to sell high):")
    if hasattr(book, 'asks') and book.asks:
        # Sort asc by price
        asks = sorted(book.asks, key=lambda x: float(x.price))[:10]
        for a in asks:
            price = float(a.price)
            size = float(a.size)
            print(f"   ${price:.2f} | Size: {size:.2f} shares {'🚨 WALL' if size > 1000 else ''}")
    else:
        print("   (Empty Ask Side)")

if __name__ == "__main__":
    analyze_walls()
