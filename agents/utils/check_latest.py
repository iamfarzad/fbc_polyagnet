import sys
import os
sys.path.append(os.getcwd())
from agents.polymarket.polymarket import Polymarket
import json
from datetime import datetime

pm = Polymarket()
# Fetch recent trades
trades = pm.get_past_trades(limit=10)

print(f"Fetched {len(trades)} trades.")
for t in trades:
    # Try to parse timestamp
    ts = t.get("matchTime") or t.get("timestamp") or 0
    try:
        dt = datetime.fromtimestamp(float(ts))
    except:
        dt = ts
    
    side = t.get("side", "UNKNOWN")
    price = t.get("price", "0")
    size = t.get("size", "0")
    asset = t.get("assetName") or t.get("asset_id")
    
    print(f"[{dt}] {side} {size} shares @ ${price} | {asset}")
