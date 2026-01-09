#!/bin/bash
source .venv/bin/activate
export PYTHONPATH="."
echo "Select Agent to Run:"
echo "1) Safe Agent (High Prob + Arb + LLM)"
echo "2) 15-Min Scalper (BTC/ETH/SOL/XRP)"
read -p "Enter choice [1]: " choice
choice=${choice:-1}

if [ "$choice" -eq "2" ]; then
    echo "Starting 15-Min Crypto Scalper (WebSocket)..."
    python3 pyml_ws_scalper.py "$@"
else
    echo "Starting Safe Agent..."
    python3 -u agents/application/pyml_trader.py "$@"
fi
