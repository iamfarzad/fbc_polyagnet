#!/bin/bash
source .venv/bin/activate
export PYTHONPATH="."

echo "Select Agent to Run:"
echo "1) Safe Agent (High Prob + Arb + LLM)"
echo "2) 15-Min Scalper (BTC/ETH/SOL/XRP)"
echo "3) Copy Trader (Follow Top Gainers)"
read -p "Enter choice [1]: " choice
choice=${choice:-1}

if [ "$choice" -eq "2" ]; then
    echo "Starting 15-Min Crypto Scalper (WebSocket)..."
    python3 -m agents.application.pyml_scalper "$@"
elif [ "$choice" -eq "3" ]; then
    echo "Starting Copy Trader..."
    python3 -m agents.application.pyml_copy_trader "$@"
else
    echo "Starting Safe Agent..."
    python3 -m agents.application.pyml_trader "$@"
fi
