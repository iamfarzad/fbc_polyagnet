import csv
import sys
from collections import defaultdict
from datetime import datetime

csv_path = "/Users/farzad/Downloads/Polymarket-Transaction-History-Tue Jan 20 2026 11_55_17 GMT+0100 (Central European Standard Time).csv"

def analyze_csv(path):
    action_counts = defaultdict(int)
    total_usdc_change = 0.0
    zero_value_txs = 0
    timestamps = []
    
    try:
        with open(path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            
            print(f"Total Rows: {len(rows)}")
            
            for row in rows:
                action = row.get('action', 'Unknown')
                usdc = float(row.get('usdcAmount', 0))
                
                action_counts[action] += 1
                total_usdc_change += usdc
                
                if usdc == 0:
                    zero_value_txs += 1
                    
                ts = row.get('timestamp')
                if ts:
                    timestamps.append(int(ts))

        print("\n--- Action Summary ---")
        for action, count in action_counts.items():
            print(f"{action}: {count}")
            
        print(f"\nTotal USDC Change (from CSV): ${total_usdc_change:.2f}")
        print(f"Zero Value Transactions: {zero_value_txs}")
        
        if timestamps:
            min_ts = min(timestamps)
            max_ts = max(timestamps)
            print(f"\nTime Range: {datetime.fromtimestamp(min_ts)} to {datetime.fromtimestamp(max_ts)}")
            print(f"Duration: {max_ts - min_ts} seconds")
            
    except Exception as e:
        print(f"Error analyzing CSV: {e}")

if __name__ == "__main__":
    analyze_csv(csv_path)
