import csv
import datetime
import os

def analyze_csv():
    csv_path = "/Users/farzad/Downloads/Polymarket-Transaction-History-Sun Jan 18 2026 10_31_46 GMT+0100 (Central European Standard Time).csv"
    report_path = "/Users/farzad/polyagent/agents/trade_report_2026_01_17_csv.md"
    
    target_date = datetime.date(2026, 1, 17)
    
    trades = []
    redeems = []
    
    print(f"Reading CSV: {csv_path}")
    
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:  # Use utf-8-sig to handle BOM
            reader = csv.DictReader(f)
            # Normalize headers just in case
            reader.fieldnames = [name.strip().strip('"') for name in reader.fieldnames] if reader.fieldnames else []
            
            for row in reader:
                try:
                    # Clean up row keys if needed
                    row = {k.strip().strip('"'): v for k, v in row.items()}
                    
                    ts = int(row['timestamp'])
                    dt = datetime.datetime.fromtimestamp(ts)
                    
                    if dt.date() == target_date:
                        action = row['action']
                        market = row['marketName']
                        amount = float(row['usdcAmount'])
                        token_outcome = row['tokenName']
                        
                        item = {
                            "time": dt.strftime("%H:%M:%S"),
                            "market": market,
                            "action": action,
                            "outcome": token_outcome,
                            "amount": amount,
                            "hash": row['hash']
                        }
                        
                        if action == "Buy":
                            trades.append(item)
                        elif action == "Redeem":
                            redeems.append(item)
                            
                except ValueError:
                    continue
                    
    except FileNotFoundError:
        print("CSV file not found!")
        return

    # Sort by time
    trades.sort(key=lambda x: x['time'], reverse=True)
    redeems.sort(key=lambda x: x['time'], reverse=True)
    
    total_spend = sum(t['amount'] for t in trades)
    total_redeemed = sum(r['amount'] for r in redeems)
    
    # Generate Markdown
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"# 📊 Verified Trade Report (2026-01-17)\n")
        f.write(f"**Source:** User-provided verification CSV\n\n")
        
        f.write(f"## 📈 Summary\n")
        f.write(f"- **Total Buys:** {len(trades)}\n")
        f.write(f"- **Total Redemptions:** {len(redeems)}\n")
        f.write(f"- **Volume Traded:** ${total_spend:.2f}\n")
        f.write(f"- **Volume Redeemed:** ${total_redeemed:.2f}\n\n")
        
        f.write(f"## 🟢 Redemptions (Wins/Payouts)\n")
        if redeems:
            f.write(f"| Time | Market | Outcome | Value (USDC) | Hash |\n")
            f.write(f"| :--- | :--- | :--- | :--- | :--- |\n")
            for r in redeems:
                short_hash = f"[{r['hash'][:6]}...](https://polygonscan.com/tx/{r['hash']})"
                f.write(f"| {r['time']} | {r['market']} | {r['outcome']} | ${r['amount']:.2f} | {short_hash} |\n")
        else:
            f.write("No redemptions recorded for this date.\n")
        
        f.write(f"\n## 🔵 Trades Executed (Buys)\n")
        if trades:
            f.write(f"| Time | Market | Outcome | Size (USDC) | Hash |\n")
            f.write(f"| :--- | :--- | :--- | :--- | :--- |\n")
            for t in trades:
                short_hash = f"[{t['hash'][:6]}...](https://polygonscan.com/tx/{t['hash']})"
                f.write(f"| {t['time']} | {t['market']} | {t['outcome']} | ${t['amount']:.2f} | {short_hash} |\n")
        else:
            f.write("No trades recorded for this date.\n")
            
    print(f"Report generated at: {report_path}")

if __name__ == "__main__":
    analyze_csv()
