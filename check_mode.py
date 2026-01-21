from agents.utils.supabase_client import get_supabase_state
import sys

def check_mode():
    state = get_supabase_state()
    if not state:
        print("Failed to connect to Supabase.")
        return

    agents = ["safe", "scalper"]
    for agent in agents:
        agent_state = state.get_agent_state(agent)
        is_dry_run = agent_state.get('is_dry_run', 'Unknown')
        print(f"Agent: {agent} | Dry Run: {is_dry_run}")

if __name__ == "__main__":
    check_mode()
