#!/bin/bash
# Quick dry run test - shows output in real-time

cd "$(dirname "$0")"
export PYTHONPATH="."
export PYTHONUNBUFFERED=1

echo "=========================================="
echo "DRY RUN TEST - Real-time Output"
echo "=========================================="
echo ""
echo "Testing each agent for 30 seconds..."
echo "Press Ctrl+C to stop"
echo ""

# Test Safe Agent
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Safe Agent (pyml_trader) - DRY RUN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
timeout 30 python3 -m agents.application.pyml_trader --dry-run 2>&1 || true
echo ""

# Test Scalper
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2. Scalper (pyml_scalper) - DRY RUN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
timeout 30 python3 -m agents.application.pyml_scalper 2>&1 || true
echo ""

# Test Copy Trader
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3. Copy Trader - DRY RUN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
timeout 30 python3 -m agents.application.pyml_copy_trader 2>&1 || true
echo ""

# Test Smart Trader
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4. Smart Trader - DRY RUN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
timeout 30 python3 -m agents.application.smart_trader 2>&1 || true
echo ""

# Test Sports Trader
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "5. Sports Trader - DRY RUN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
timeout 30 python3 -m agents.application.sports_trader 2>&1 || true
echo ""

# Test Esports Trader
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "6. Esports Trader - DRY RUN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
timeout 30 python3 -m agents.application.esports_trader 2>&1 || true
echo ""

echo "=========================================="
echo "TEST COMPLETE"
echo "=========================================="
