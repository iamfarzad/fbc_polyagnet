#!/usr/bin/env python3
"""
FULL STACK TEST: Backend + Frontend + WebSocket + Trading Logic
Tests the complete Polymarket trading system end-to-end
"""

import os
import sys
import json
import time
import requests
import websocket
import threading
from datetime import datetime

# Test Configuration
BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"
WS_URL = "ws://localhost:8000/ws/dashboard"

def test_backend_api():
    """Test backend API endpoints"""
    print("🔧 Testing Backend API...")

    tests = [
        ("Health Check", f"{BACKEND_URL}/api/health"),
        ("Dashboard Data", f"{BACKEND_URL}/api/dashboard"),
        ("Agent Status", f"{BACKEND_URL}/api/positions"),
        ("OpenAPI Schema", f"{BACKEND_URL}/openapi.json"),
    ]

    results = {}
    for test_name, url in tests:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                results[test_name] = {"status": "✅ PASS", "code": response.status_code}
                print(f"  ✅ {test_name}: {response.status_code}")
            else:
                results[test_name] = {"status": "❌ FAIL", "code": response.status_code, "error": response.text[:100]}
                print(f"  ❌ {test_name}: {response.status_code} - {response.text[:50]}...")
        except Exception as e:
            results[test_name] = {"status": "❌ ERROR", "error": str(e)}
            print(f"  ❌ {test_name}: {str(e)}")

    return results

def test_frontend_connectivity():
    """Test frontend loading and API connections"""
    print("🌐 Testing Frontend Connectivity...")

    try:
        response = requests.get(FRONTEND_URL, timeout=10)
        if response.status_code == 200:
            print("  ✅ Frontend loads successfully")

            # Check for API connection indicators in HTML
            if "Polyagent Dashboard" in response.text:
                print("  ✅ Frontend title correct")
            else:
                print("  ⚠️ Frontend title not found")

            return {"status": "✅ PASS", "code": response.status_code}
        else:
            print(f"  ❌ Frontend failed: {response.status_code}")
            return {"status": "❌ FAIL", "code": response.status_code}
    except Exception as e:
        print(f"  ❌ Frontend error: {str(e)}")
        return {"status": "❌ ERROR", "error": str(e)}

def test_websocket_connection():
    """Test WebSocket connectivity"""
    print("📡 Testing WebSocket Connection...")

    ws_connected = False
    ws_messages = []
    ws_errors = []

    def on_message(ws, message):
        ws_messages.append(message)
        print(f"  📨 WS Message: {message[:100]}...")

    def on_error(ws, error):
        ws_errors.append(str(error))
        print(f"  ❌ WS Error: {error}")

    def on_open(ws):
        nonlocal ws_connected
        ws_connected = True
        print("  ✅ WebSocket connected")
        # Close after a moment
        time.sleep(1)
        ws.close()

    try:
        ws = websocket.WebSocketApp(
            WS_URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error
        )

        # Run WebSocket in thread with timeout
        ws_thread = threading.Thread(target=lambda: ws.run_forever(ping_timeout=5))
        ws_thread.daemon = True
        ws_thread.start()

        # Wait for connection
        time.sleep(3)

        if ws_connected:
            return {"status": "✅ PASS", "messages": len(ws_messages), "errors": ws_errors}
        else:
            return {"status": "❌ NO CONNECTION", "errors": ws_errors}

    except Exception as e:
        return {"status": "❌ ERROR", "error": str(e)}

def test_market_discovery():
    """Test the centralized market discovery functionality"""
    print("🔍 Testing Market Discovery...")

    try:
        # Import the centralized discovery
        sys.path.insert(0, 'agents')
        from agents.polymarket.gamma import GammaMarketClient

        gamma = GammaMarketClient()
        markets = gamma.discover_15min_crypto_markets()

        if markets:
            print(f"  ✅ Found {len(markets)} markets")
            assets = set(m['asset'] for m in markets)
            print(f"  📊 Assets: {', '.join(sorted(assets))}")

            # Check market structure
            required_fields = ['id', 'question', 'asset', 'up_token', 'down_token', 'end_date']
            sample_market = markets[0]
            missing_fields = [f for f in required_fields if f not in sample_market]

            if not missing_fields:
                print("  ✅ Market structure correct")
                return {"status": "✅ PASS", "markets": len(markets), "assets": list(assets)}
            else:
                print(f"  ❌ Missing fields: {missing_fields}")
                return {"status": "❌ STRUCTURE ERROR", "missing": missing_fields}
        else:
            print("  ❌ No markets found")
            return {"status": "❌ NO MARKETS"}

    except Exception as e:
        print(f"  ❌ Market discovery error: {e}")
        return {"status": "❌ ERROR", "error": str(e)}

def test_agent_integration():
    """Test agent status and integration"""
    print("🤖 Testing Agent Integration...")

    try:
        response = requests.get(f"{BACKEND_URL}/api/dashboard", timeout=10)
        if response.status_code == 200:
            data = response.json()
            agents = data.get('agents', {})

            if agents:
                print(f"  ✅ Found {len(agents)} agents")
                for agent_name, agent_data in agents.items():
                    status = agent_data.get('status', 'unknown')
                    print(f"    {agent_name}: {status}")
                return {"status": "✅ PASS", "agents": len(agents)}
            else:
                print("  ⚠️ No agents found (may be normal)")
                return {"status": "⚠️ NO AGENTS"}
        else:
            print(f"  ❌ Dashboard API failed: {response.status_code}")
            return {"status": "❌ API FAIL", "code": response.status_code}

    except Exception as e:
        print(f"  ❌ Agent integration error: {e}")
        return {"status": "❌ ERROR", "error": str(e)}

def test_full_lifecycle():
    """Test complete trading lifecycle (without actual trades due to library issues)"""
    print("🔄 Testing Full Lifecycle Logic...")

    # This tests the logic without executing real trades
    try:
        # Import trading components
        sys.path.insert(0, 'agents')
        from agents.polymarket.gamma import GammaMarketClient

        # Test discovery
        gamma = GammaMarketClient()
        markets = gamma.discover_15min_crypto_markets()

        if markets:
            print(f"  ✅ Discovery works: {len(markets)} markets")

            # Test order structure (without execution)
            sample_market = markets[0]
            required_order_fields = ['up_token', 'down_token', 'end_date', 'fee_bps']

            has_fields = all(field in sample_market for field in required_order_fields)
            if has_fields:
                print("  ✅ Order structure complete")
                print(f"    Sample: {sample_market['asset']} - Fee: {sample_market.get('fee_bps', 'unknown')}")

                return {"status": "✅ PASS", "markets_ready": len(markets)}
            else:
                missing = [f for f in required_order_fields if f not in sample_market]
                print(f"  ❌ Missing order fields: {missing}")
                return {"status": "❌ STRUCTURE INCOMPLETE", "missing": missing}
        else:
            print("  ❌ No markets available")
            return {"status": "❌ NO MARKETS"}

    except Exception as e:
        print(f"  ❌ Lifecycle test error: {e}")
        return {"status": "❌ ERROR", "error": str(e)}

def main():
    """Run complete full stack test"""
    print("="*80)
    print("🚀 FULL STACK TEST: Polymarket Trading System")
    print("="*80)
    print(f"Backend: {BACKEND_URL}")
    print(f"Frontend: {FRONTEND_URL}")
    print(f"WebSocket: {WS_URL}")
    print("="*80)

    results = {}

    # Test each component
    results['backend'] = test_backend_api()
    print()
    results['frontend'] = test_frontend_connectivity()
    print()
    results['websocket'] = test_websocket_connection()
    print()
    results['discovery'] = test_market_discovery()
    print()
    results['agents'] = test_agent_integration()
    print()
    results['lifecycle'] = test_full_lifecycle()

    # Summary
    print("\n" + "="*80)
    print("📊 TEST SUMMARY")
    print("="*80)

    all_pass = True
    for test_name, result in results.items():
        status = result.get('status', 'UNKNOWN')
        print("<15")
        if '❌' in status:
            all_pass = False

    print("="*80)
    if all_pass:
        print("🎉 ALL TESTS PASSED - Full stack is operational!")
    else:
        print("⚠️ Some tests failed - Check results above")
        print("Note: Trading execution blocked by py-clob-client library issue")
    print("="*80)

    return results

if __name__ == "__main__":
    main()