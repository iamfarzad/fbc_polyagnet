"""
Test suite for HedgeFundAnalyst with LLM integration.
Tests social signal checks, mistake learning, and trade analysis.
"""

import os
import sys
import logging
import json
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'application'))

from hedge_fund_analyst import HedgeFundAnalyst
from smart_context import SmartContext

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestHedgeFundAnalyst")


def test_social_signals_rejection():
    """Test that strongly negative comment sentiment triggers rejection."""
    print("\n=== Test: Social Signals - Negative Sentiment Rejection ===")
    
    analyst = HedgeFundAnalyst()
    
    # Mock context with negative sentiment
    context = {
        "wallet": {"cash": 1000, "daily_pnl": 0},
        "performance": {"current_mood": "NEUTRAL", "win_rate": "50%"},
        "market_depth": {},
        "sentiment": {"global_trend": "NEUTRAL"},
        "comment_sentiment": {"sentiment_score": -0.8, "comment_count": 50},
        "whale_positions": {}
    }
    
    # Proposed trade
    trade = {
        "ticker": "TEST",
        "side": "YES",
        "odds": 0.5,
        "edge": 0.05,
        "market_question": "Will this test pass?"
    }
    
    # Test social signal check
    result = analyst._check_social_signals(trade, context)
    
    assert result is not None, "Social check should return a result"
    assert result["decision"] == "REJECTED", "Should reject due to negative sentiment"
    assert "negative comment sentiment" in result["reasoning"].lower(), "Reasoning should mention sentiment"
    
    print(f"✓ Test passed: {result}")
    return True


def test_social_signals_warning():
    """Test that moderately negative sentiment logs warning but doesn't reject."""
    print("\n=== Test: Social Signals - Moderate Sentiment Warning ===")
    
    analyst = HedgeFundAnalyst()
    
    # Mock context with moderate negative sentiment
    context = {
        "wallet": {"cash": 1000, "daily_pnl": 0},
        "performance": {"current_mood": "NEUTRAL", "win_rate": "50%"},
        "market_depth": {},
        "sentiment": {"global_trend": "NEUTRAL"},
        "comment_sentiment": {"sentiment_score": -0.4, "comment_count": 30},
        "whale_positions": {}
    }
    
    trade = {
        "ticker": "TEST",
        "side": "YES",
        "odds": 0.5,
        "edge": 0.05,
        "market_question": "Will this test pass?"
    }
    
    # Should return None (no hard rejection)
    result = analyst._check_social_signals(trade, context)
    
    assert result is None, "Should not reject for moderate negative sentiment"
    
    print("✓ Test passed: Moderate sentiment does not trigger hard rejection")
    return True


def test_whale_position_conflict():
    """Test that whale position conflicts are detected."""
    print("\n=== Test: Whale Position Conflict ===")
    
    analyst = HedgeFundAnalyst()
    
    # Mock context with whale positions
    context = {
        "wallet": {"cash": 1000, "daily_pnl": 0},
        "performance": {"current_mood": "NEUTRAL", "win_rate": "50%"},
        "market_depth": {},
        "sentiment": {"global_trend": "NEUTRAL"},
        "comment_sentiment": {"sentiment_score": 0.0},
        "whale_positions": {"dominant_side": "NO", "whale_count": 5, "total_volume": 10000}
    }
    
    trade = {
        "ticker": "TEST",
        "side": "YES",  # We want YES, but whales are on NO
        "odds": 0.5,
        "edge": 0.05,
        "market_question": "Will this test pass?"
    }
    
    result = analyst._check_social_signals(trade, context)
    
    # Should return None (soft rejection, not hard)
    assert result is None, "Whale conflict should not hard reject"
    
    print("✓ Test passed: Whale conflict detected but not hard rejected")
    return True


def test_mistake_analyzer_integration():
    """Test that MistakeAnalyzer is properly initialized and used."""
    print("\n=== Test: MistakeAnalyzer Integration ===")
    
    analyst = HedgeFundAnalyst()
    
    # Check if MistakeAnalyzer was initialized
    assert analyst.mistake_analyzer is not None, "MistakeAnalyzer should be initialized"
    assert analyst.agent_name == "hedge_fund_analyst", "Agent name should be set"
    
    print("✓ Test passed: MistakeAnalyzer initialized correctly")
    return True


def test_full_analysis_flow():
    """Test the complete analyze_trade_opportunity flow."""
    print("\n=== Test: Full Analysis Flow ===")
    
    analyst = HedgeFundAnalyst()
    
    # Mock context
    context = {
        "wallet": {"cash": 1000, "daily_pnl": 0},
        "performance": {"current_mood": "NEUTRAL", "win_rate": "50%"},
        "market_depth": {},
        "sentiment": {"global_trend": "NEUTRAL"},
        "comment_sentiment": {"sentiment_score": 0.0},
        "whale_positions": {}
    }
    
    # Proposed trade
    trade = {
        "ticker": "BTC",
        "side": "YES",
        "odds": 0.6,
        "edge": 0.1,
        "market_question": "Will BTC reach $100k by end of year?"
    }
    
    # Run analysis (will use fallback logic since no API key)
    result = analyst.analyze_trade_opportunity(context, trade)
    
    assert result is not None, "Should return a result"
    assert "decision" in result, "Should have decision"
    assert "confidence" in result, "Should have confidence"
    assert "risk_adjustment_factor" in result, "Should have risk adjustment factor"
    assert "reasoning" in result, "Should have reasoning"
    
    print(f"✓ Test passed: {result}")
    return True


def test_fallback_logic():
    """Test fallback logic gates."""
    print("\n=== Test: Fallback Logic ===")
    
    analyst = HedgeFundAnalyst()
    
    # Test 1: Cold streak reduces size
    context_cold = {
        "wallet": {"cash": 1000, "daily_pnl": -100},
        "performance": {"current_mood": "COLD_STREAK", "win_rate": "20%"},
        "market_depth": {"spread": 0.01},
        "sentiment": {"global_trend": "NEUTRAL"}
    }
    
    trade = {"ticker": "TEST", "side": "YES", "odds": 0.5, "edge": 0.05}
    result = analyst._fallback_logic(context_cold, trade)
    
    assert result["decision"] == "REDUCE_SIZE", "Should reduce size in cold streak"
    assert result["risk_adjustment_factor"] == 0.5, "Should halve size in cold streak"
    
    # Test 2: Wide spread rejects
    context_wide = {
        "wallet": {"cash": 1000, "daily_pnl": 0},
        "performance": {"current_mood": "NEUTRAL", "win_rate": "50%"},
        "market_depth": {"spread": 0.08},  # 8% spread
        "sentiment": {"global_trend": "NEUTRAL"}
    }
    
    result = analyst._fallback_logic(context_wide, trade)
    assert result["decision"] == "REJECTED", "Should reject wide spread"
    assert result["risk_adjustment_factor"] == 0.0, "Should zero out position"
    
    # Test 3: Hot streak increases size
    context_hot = {
        "wallet": {"cash": 1000, "daily_pnl": 100},
        "performance": {"current_mood": "HOT_STREAK", "win_rate": "80%"},
        "market_depth": {"spread": 0.01},
        "sentiment": {"global_trend": "NEUTRAL"}
    }
    
    result = analyst._fallback_logic(context_hot, trade)
    assert result["risk_adjustment_factor"] == 1.2, "Should increase size in hot streak"
    
    print("✓ Test passed: All fallback logic gates working correctly")
    return True


def test_smart_context():
    """Test SmartContext with social signals."""
    print("\n=== Test: SmartContext ===")
    
    smart_ctx = SmartContext()
    
    # Test full context
    context = smart_ctx.get_full_context(
        market_data={"bids": [{"price": 0.5, "size": 100}], "asks": [{"price": 0.51, "size": 100}]},
        market_question="Will AI revolutionize trading by 2025?"
    )
    
    assert "wallet" in context, "Should have wallet info"
    assert "performance" in context, "Should have performance info"
    assert "market_depth" in context, "Should have market depth"
    assert "sentiment" in context, "Should have sentiment"
    assert "whale_positions" in context, "Should have whale positions"
    assert "comment_sentiment" in context, "Should have comment sentiment"
    assert "market_question" in context, "Should have market question"
    
    # Check comment sentiment was analyzed
    assert "sentiment_score" in context["comment_sentiment"], "Should have sentiment score"
    
    print(f"✓ Test passed: SmartContext includes all fields")
    print(f"  - Sentiment score: {context['comment_sentiment']['sentiment_score']}")
    return True


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("HedgeFundAnalyst Test Suite")
    print("="*60)
    
    tests = [
        test_social_signals_rejection,
        test_social_signals_warning,
        test_whale_position_conflict,
        test_mistake_analyzer_integration,
        test_full_analysis_flow,
        test_fallback_logic,
        test_smart_context
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
        except AssertionError as e:
            print(f"✗ Test failed: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ Test error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
