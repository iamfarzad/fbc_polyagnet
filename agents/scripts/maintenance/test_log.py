import sys
import os
sys.path.append(os.getcwd())
from agents.utils.supabase_client import get_supabase_state
from agents.utils.context import LLMActivity
import uuid
import datetime

print("Testing Supabase Connectivity...")
try:
    supa = get_supabase_state()
    # Attempt to log
    success = supa.log_llm_activity(
        agent="TEST_BOT",
        action_type="CONNECTIVITY_CHECK",
        market_question="Can we write to DB?",
        prompt_summary="Testing write permissions",
        reasoning="Diagnostics",
        conclusion="TEST",
        confidence=1.0,
        duration_ms=100
    )
    print(f"Write Result: {success}")
    
    # Attempt to read
    print("Testing Read...")
    activities = supa.get_llm_activity(limit=5, agent="TEST_BOT")
    print(f"Read Result Count: {len(activities)}")
    if activities:
        print(f"Last Activity: {activities[0]['action_type']}")
except Exception as e:
    print(f"Exception: {e}")
