
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.utils.risk_engine import calculate_ev, kelly_size, check_drawdown

def run_tests():
    print("🧪 Testing Risk Engine...\n")

    # 1. Test EV Calculation
    print("1. Testing EV Calculation:")
    # Scenario: Price 0.60, Win Prob 0.75 (Edge!), Fee 0.02
    # Profit if win: 0.40. Loss if lose: 0.60.
    # EV = (0.75 * 0.40) - (0.25 * 0.60) - 0.02
    # EV = 0.30 - 0.15 - 0.02 = 0.13.
    ev = calculate_ev(0.60, 0.75, 0.40, fees=0.02)
    print(f"  - Case A (Good Bet): Price 0.60, Prob 0.75 -> EV: {ev:.4f} (Expected ~0.13)")
    assert 0.12 < ev < 0.14, "EV Calc Failed Case A"

    # Scenario: Price 0.80, Win Prob 0.75 (Bad Bet), Fee 0.02
    # Profit: 0.20. Loss: 0.80.
    # EV = (0.75 * 0.20) - (0.25 * 0.80) - 0.02
    # EV = 0.15 - 0.20 - 0.02 = -0.07. Should return 0.0 (max(0, ev))
    ev_bad = calculate_ev(0.80, 0.75, 0.20, fees=0.02)
    print(f"  - Case B (Bad Bet): Price 0.80, Prob 0.75 -> EV: {ev_bad:.4f} (Expected 0.0)")
    assert ev_bad == 0.0, "EV Calc Failed Case B"
    print("  ✅ EV Calculation Passed\n")

    # 2. Test Kelly Sizing (Half-Kelly)
    print("2. Testing Kelly Sizing:")
    # Case A EV = 0.13. Price 0.60.
    # Kelly_f = 0.13 / (1 - 0.60) = 0.13 / 0.40 = 0.325
    # Half-Kelly = 0.1625
    # Max Risk = 0.02 (2%). So should cap at 0.02.
    balance = 100.0
    size = kelly_size(balance, 0.13, 0.60, max_risk_pct=0.02)
    print(f"  - Case A (Cap Risk): Bal $100, EV 0.13 -> Size: ${size:.2f} (Expected $2.00)")
    assert abs(size - 2.00) < 0.01, f"Kelly Failed Case A: Got {size}"
    
    # Case C (Small Edge, No Cap): Max Risk 25% for test
    # EV 0.13, Price 0.60 -> Half Kelly 16.25%.
    size_uncapped = kelly_size(balance, 0.13, 0.60, max_risk_pct=0.25)
    print(f"  - Case B (Uncapped): Bal $100, EV 0.13 -> Size: ${size_uncapped:.2f} (Expected ~$16.25)")
    assert abs(size_uncapped - 16.25) < 0.05, f"Kelly Failed Case B: Got {size_uncapped}"
    
    # Case D (Tiny Size Floor): Calculated size < $0.10
    # Balance $1. EV 0.05, Price 0.5. Kelly_f = 0.1. Half = 0.05. Size = $0.05.
    # Should floor to 0.0
    size_tiny = kelly_size(1.0, 0.05, 0.50, max_risk_pct=0.10)
    print(f"  - Case C (Floor): Bal $1, Calc Size $0.05 -> Size: ${size_tiny:.2f} (Expected 0.00)")
    assert size_tiny == 0.0, f"Kelly Failed Case C: Got {size_tiny}"
    print("  ✅ Kelly Sizing Passed\n")

    # 3. Test Drawdown
    print("3. Testing Drawdown:")
    # Initial 100, Current 96. Drawdown 4%. Limit 5%. -> True (Safe)
    safe = check_drawdown(100, 96, 0.05)
    print(f"  - Case A (Safe): 4% Drawdown < 5% Limit -> {safe}")
    assert safe == True, "Drawdown Failed Case A"
    
    # Initial 100, Current 94. Drawdown 6%. Limit 5%. -> False (Stop)
    unsafe = check_drawdown(100, 94, 0.05)
    print(f"  - Case B (Unsafe): 6% Drawdown > 5% Limit -> {unsafe}")
    assert unsafe == False, "Drawdown Failed Case B"
    print("  ✅ Drawdown Logic Passed\n")

    print("🎉 All Risk Engine Tests Passed!")

if __name__ == "__main__":
    run_tests()
