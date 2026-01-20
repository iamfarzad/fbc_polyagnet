import csv
import os
import time
from agents.utils.supabase_client import get_supabase_state

CSV_PATH = "/Users/farzad/Downloads/Polymarket-Transaction-History-Tue Jan 20 2026 11_55_17 GMT+0100 (Central European Standard Time).csv"

def ingest_history():
    supa = get_supabase_state()
    if not supa:
        print("❌ Supabase client not available.")
        return

    print("🚀 Ingesting Transaction History to Supabase...")
    
    with open(CSV_PATH, 'r') as f:
        reader = csv.DictReader(f)
        count = 0
        
        for row in reader:
            action = row.get('action')
            if action != 'Buy':
                continue # Only analyze Buys for now
                
            market = row.get('marketName')
            outcome = row.get('tokenName')
            amount_usd = float(row.get('usdcAmount', 0))
            token_amount = float(row.get('tokenAmount', 0))
            price = amount_usd / token_amount if token_amount > 0 else 0
            ts = row.get('timestamp')
            
            # Convert timestamp
            # CSV ts is likely seconds. Supabase expects ISO string? 
            # Actually Supabase client might handle it, or we format it.
            # Let's assume generated ID is needed.
            
            trade_data = {
                "agent": "scalper", # Assuming Scalper for now based on investigation
                "market_question": market,
                "outcome": outcome,
                "size_usd": amount_usd,
                "price": price,
                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(int(ts))),
                "status": "filled",
                "pnl": -amount_usd, # Default to loss until verified? Or let Analyzer check result?
                # MistakeAnalyzer checks result comparing outcome to 'actual'.
                # We interpret "Buy" as an executed trade.
                # We need to know if it WON or LOST.
                # For now, we ingest it as a "filled" trade.
                "market_id": "csv_import" 
            }
            
            # Insert into Supabase
            try:
                supa.client.table('trades').insert(trade_data).execute()
                print(f"✅ Ingested: {market} (${amount_usd})")
                count += 1
            except Exception as e:
                print(f"⚠️ Failed to insert: {e}")
                
        print(f"🎉 Processed {count} trades.")

if __name__ == "__main__":
    ingest_history()
