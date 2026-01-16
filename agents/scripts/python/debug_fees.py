import requests
import json

def debug_fees():
    print("🔍 Scanning ALL active markets for ANY fee > 0...")
    url = "https://gamma-api.polymarket.com/markets"
    params = {
        "active": "true",
        "closed": "false",
        "limit": 100,
        "offset": 0
    }
    
    found = 0
    checked = 0
    
    while checked < 1000:
        resp = requests.get(url, params=params, timeout=5)
        markets = resp.json()
        if not markets: break
        
        print(f"   Fetching offset {params['offset']}...")
        
        for m in markets:
            checked += 1
            clob_ids = json.loads(m.get("clobTokenIds", "[]"))
            if not clob_ids: continue
            
            token_id = clob_ids[0]
            fee_r = requests.get(f"https://clob.polymarket.com/fee-rate?token_id={token_id}").json()
            bps = int(fee_r.get("fee_rate_bps", 0))
            
            if bps > 0:
                print(f"   💰 FOUND FEE: {bps} bps | {m['question']}")
                found += 1
            
            # Print sample every 50 to ensure we are looking at right markets
            if checked % 50 == 0:
                print(f"      Checked {checked} markets... (Sample: {m['question']})")
                
        params["offset"] += 100
        if found > 5: break # Stop if we found fees
        
    print(f"   ✅ Done. Found {found} fee markets out of {checked}.")

if __name__ == "__main__":
    debug_fees()
