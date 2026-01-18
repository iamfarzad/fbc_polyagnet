import re
from datetime import datetime

def parse_ledger_value(val_str):
    if not val_str or val_str == "-": return 0.0
    return float(val_str.replace('$', '').replace(',', ''))

def analyze_esports():
    ledger_path = "/Users/farzad/polyagent/agents/full_ledger.md"
    
    esports_trades = []
    redemptions = []
    
    # Keywords for esports markets
    keywords = ["LoL:", "Dota 2:", "CS2:", "Counter-Strike:", "Valorant:", "(BO1)", "(BO3)", "(BO5)"]
    
    print(f"Analyzing {ledger_path} for Esports activity...")
    
    try:
        with open(ledger_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        for line in lines:
            if not line.startswith("| 2026"): continue
            
            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 8: continue
            
            # Extract fields (indexes shifted by +1 because startswith |)
            date_str = parts[1]
            txn_type = parts[2]
            market = parts[3]
            side = parts[4]
            outcome = parts[5]
            value_str = parts[8] # Value (USDC) column
            
            # Filter for Esports
            is_esports = any(k in market for k in keywords)
            
            if is_esports:
                amount = parse_ledger_value(value_str)
                
                item = {
                    "date": date_str,
                    "market": market,
                    "type": txn_type,
                    "side": side,
                    "outcome": outcome,
                    "amount": amount
                }
                
                if txn_type == "TRADE":
                    esports_trades.append(item)
                elif txn_type == "REDEEM":
                    redemptions.append(item)
                    
    except FileNotFoundError:
        print("Ledger file not found!")
        return

    # Sort
    esports_trades.sort(key=lambda x: x['date'], reverse=True)
    
    total_invested = sum(t['amount'] for t in esports_trades if t['side'] == "BUY") # Only buy side costs money
    money_redeemed = sum(r['amount'] for r in redemptions)
    
    # Generate Report
    report_path = "/Users/farzad/polyagent/agents/esports_report.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# 🎮 Esports Trader Performance Report\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("## 🏆 Performance Overview\n")
        f.write(f"- **Total Bets Placed:** {len(esports_trades)}\n")
        f.write(f"- **Total Volume Invested:** ${total_invested:.2f}\n")
        f.write(f"- **Total Redeemed (Wins):** ${money_redeemed:.2f}\n")
        
        pnl = money_redeemed - total_invested
        roi = (pnl / total_invested * 100) if total_invested > 0 else 0
        
        symbol = "🟢" if pnl >= 0 else "🔴"
        f.write(f"- **Net PnL:** {symbol} ${pnl:.2f}\n")
        f.write(f"- **ROI:** {roi:.1f}%\n\n")
        
        f.write("## 🕹️ Recent Trades\n")
        if esports_trades:
            f.write("| Date | Market | Side | Outcome | Value |\n")
            f.write("| :--- | :--- | :--- | :--- | :--- |\n")
            for t in esports_trades[:20]: # Show last 20
                f.write(f"| {t['date']} | {t['market']} | {t['side']} | {t['outcome']} | ${t['amount']:.2f} |\n")
        else:
            f.write("No esports trades found.\n")
            
        f.write("\n## 💰 Recent Redemptions\n")
        if redemptions:
            f.write("| Date | Market | Value |\n")
            f.write("| :--- | :--- | :--- |\n")
            for r in redemptions:
                f.write(f"| {r['date']} | {r['market']} | ${r['amount']:.2f} |\n")
        else:
            f.write("No redemptions found.\n")

    print(f"Report generated: {report_path}")

if __name__ == "__main__":
    analyze_esports()
