
import os
import sys
from dotenv import load_dotenv

# Add path to agents
sys.path.append(os.path.join(os.getcwd(), "agents"))

try:
    from agents.agents.utils.supabase_client import get_supabase_state
except ImportError:
    from agents.utils.supabase_client import get_supabase_state

def check_logs():
    load_dotenv()
    supa = get_supabase_state()
    
    print("--- 1. Checking 'agent_activity' (LLM Logs) ---")
    try:
        logs = supa.get_llm_activity(limit=5)
        print(f"Found {len(logs)} logs.")
        for log in logs:
            print(f"[{log.get('timestamp')}] {log.get('agent')} -> {log.get('action_type')}")
    except Exception as e:
        print(f"Error fetching logs: {e}")

    print("\n--- 2. Checking 'agent_state' ---")
    try:
        # Assuming simple table query if method doesn't exist, but let's try a known method or raw query if possible
        # checking safe state
        state = supa.get_agent_state("safe")
        print(f"Safe Agent State: {state}")
    except Exception as e:
        print(f"Error fetching state: {e}")

if __name__ == "__main__":
    check_logs()
