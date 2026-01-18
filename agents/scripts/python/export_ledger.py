import os
import sys
import requests
import csv
from datetime import datetime
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
    # Check for Proxy Address first
    proxy_address = os.getenv("POLYMARKET_PROXY_ADDRESS")
    if proxy_address:
        address = proxy_address
        print(f"Using Proxy Address: {address}")
    else:
        address = poly.get_address_for_private_key()
        print(f"Using EOA Address: {address}")
    
    print(f"Fetching complete activity for {address}...")
    
    all_activities = []
    limit = 100
    offset = 0
    
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
        except Exception as e:
            print(f"Error fetching activity: {e}")
            break
    
    print(f"Found {len(all_activities)} transactions.")
    
    # Sort by timestamp descending
    all_activities.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    
    # Define Report Path
    report_path = os.path.join(project_root, "agents/full_ledger.md")
    
    # Generate Markdown Table
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 📒 Full Transaction Ledger\n\n")
        f.write(f"**Address:** `{address}`\n")
        f.write(f"**Date Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("| Date | Type | Market | Side | Outcome | Size | Price | Value (USDC) | Hash |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        
        for act in all_activities:
            ts = act.get('timestamp')
            date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else "N/A"
            txn_type = act.get('type', 'UNKNOWN')
            title = act.get('title', 'Unknown Market').replace("|", "-") # Escape pipes
            side = act.get('side', '-')
            outcome = act.get('outcome', '-')
            size = act.get('size', 0)
            price = act.get('price', 0)
            usdc = act.get('usdcSize', 0)
            tx_hash = act.get('transactionHash', '')
            short_hash = f"[{tx_hash[:6]}...](https://polygonscan.com/tx/{tx_hash})" if tx_hash else "-"
            
            # Format numbers
            size_fmt = f"{size:,.2f}"
            price_fmt = f"${price:.2f}" if price else "-"
            usdc_fmt = f"${usdc:,.2f}"
            
            f.write(f"| {date_str} | {txn_type} | {title} | {side} | {outcome} | {size_fmt} | {price_fmt} | {usdc_fmt} | {short_hash} |\n")
            
    print(f"✅ Ledger exported to: {report_path}")

if __name__ == "__main__":
    main()
