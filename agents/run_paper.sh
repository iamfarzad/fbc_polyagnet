#!/bin/bash
# run_paper.sh - Run all agents in paper trading mode

# Ensure dry run is forced
export MIN_EDGE_PERCENT=0.01
export PYTHONPATH=$PYTHONPATH:.

echo "🚀 Starting PAPER TRADING Session (10 Hours)..."
echo "------------------------------------------------"

# Kill any existing agents
pkill -f "python agents/application/esports_trader.py"
pkill -f "python agents/application/pyml_scalper.py"
pkill -f "python agents/application/smart_trader.py"

# Start Esports Trader
echo "🎮 Starting Esports Trader..."
nohup python agents/application/esports_trader.py > esports_paper.log 2>&1 &
echo "   PID: $!"

# Start Scalper
echo "⚡ Starting Hybrid Scalper..."
nohup python agents/application/pyml_scalper.py > scalper_paper.log 2>&1 &
echo "   PID: $!"

# Start Smart Trader
echo "🧠 Starting Smart Trader..."
nohup python agents/application/smart_trader.py > smart_paper.log 2>&1 &
echo "   PID: $!"

echo "------------------------------------------------"
echo "✅ All agents running in background."
echo "📜 Logs: esports_paper.log, scalper_paper.log, smart_paper.log"
echo "📊 Run 'python agents/paper_perf.py' to see results."
