#!/usr/bin/env python3
import sys
sys.path.append('agents')
sys.path.append('agents/agents')

try:
    from agents.application.sports_trader import SportsTrader
    print('✅ Sports trader import successful')
    trader = SportsTrader(dry_run=True)
    print('✅ Sports trader initialization successful')
    print('.2f')
except Exception as e:
    print(f'❌ Sports trader error: {e}')
    import traceback
    traceback.print_exc()