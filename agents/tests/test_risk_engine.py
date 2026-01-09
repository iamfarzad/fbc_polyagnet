"""
Unit tests for Risk Engine functions.

Run with: python -m pytest tests/test_risk_engine.py -v
Or: python tests/test_risk_engine.py
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.utils.risk_engine import calculate_ev, kelly_size, check_drawdown


class TestCalculateEV(unittest.TestCase):
    """Tests for Expected Value calculation"""
    
    def test_positive_ev_good_bet(self):
        """Price 0.60, Win Prob 0.75 -> Positive EV"""
        ev = calculate_ev(0.60, 0.75, 0.40, fees=0.02)
        self.assertAlmostEqual(ev, 0.13, places=2)
    
    def test_negative_ev_returns_zero(self):
        """Bad bet should return 0.0 (not negative)"""
        ev = calculate_ev(0.80, 0.75, 0.20, fees=0.02)
        self.assertEqual(ev, 0.0)
    
    def test_edge_case_price_zero(self):
        """Price 0 should return 0"""
        ev = calculate_ev(0.0, 0.75, 0.40)
        self.assertEqual(ev, 0.0)
    
    def test_edge_case_price_one(self):
        """Price 1.0 should return 0"""
        ev = calculate_ev(1.0, 0.75, 0.40)
        self.assertEqual(ev, 0.0)
    
    def test_high_prob_high_price(self):
        """95% probability at 0.90 price (high prob grinding strategy)"""
        ev = calculate_ev(0.90, 0.95, 0.10, fees=0.01)
        self.assertGreater(ev, 0.03)


class TestKellySize(unittest.TestCase):
    """Tests for Kelly Criterion position sizing"""
    
    def test_size_capped_by_max_risk(self):
        """Size should be capped at max_risk_pct * balance"""
        size = kelly_size(100.0, 0.13, 0.60, max_risk_pct=0.02)
        self.assertAlmostEqual(size, 2.00, places=2)
    
    def test_size_uncapped(self):
        """With high max_risk, Kelly should calculate freely"""
        size = kelly_size(100.0, 0.13, 0.60, max_risk_pct=0.25)
        self.assertAlmostEqual(size, 16.25, places=1)
    
    def test_tiny_size_floors_to_zero(self):
        """Sizes < $0.10 should floor to 0"""
        size = kelly_size(1.0, 0.05, 0.50, max_risk_pct=0.10)
        self.assertEqual(size, 0.0)
    
    def test_zero_ev_returns_zero(self):
        """Zero EV should return zero size"""
        size = kelly_size(100.0, 0.0, 0.50)
        self.assertEqual(size, 0.0)
    
    def test_zero_balance_returns_zero(self):
        """Zero balance should return zero size"""
        size = kelly_size(0.0, 0.13, 0.50)
        self.assertEqual(size, 0.0)
    
    def test_minimum_bet_floor(self):
        """Size between $0.10-$0.50 should floor to $0.50"""
        size = kelly_size(10.0, 0.10, 0.50, max_risk_pct=0.05)
        self.assertEqual(size, 0.50)


class TestCheckDrawdown(unittest.TestCase):
    """Tests for drawdown limit checking"""
    
    def test_within_limit_is_safe(self):
        """4% drawdown with 5% limit -> True (safe)"""
        result = check_drawdown(100, 96, 0.05)
        self.assertTrue(result)
    
    def test_exceeds_limit_is_unsafe(self):
        """6% drawdown with 5% limit -> False (stop)"""
        result = check_drawdown(100, 94, 0.05)
        self.assertFalse(result)
    
    def test_exact_limit_is_safe(self):
        """Exactly at limit should still be safe"""
        result = check_drawdown(100, 95, 0.05)
        self.assertTrue(result)
    
    def test_zero_initial_returns_true(self):
        """Edge case: zero initial balance"""
        result = check_drawdown(0, 50, 0.05)
        self.assertTrue(result)
    
    def test_profit_is_safe(self):
        """No drawdown (profit) should be safe"""
        result = check_drawdown(100, 110, 0.05)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
