"""
5-Agent Orchestrator with Auto-Restart
Runs: Safe, Scalper, Copy, Sports, Esports
"""
import multiprocessing
import os
import signal
import sys
print("   🚀 AGENT STARTING... PYTHONPATH=" + str(sys.path))

import time
import subprocess
from datetime import datetime

# Agent configs: (module, args, restart_delay)
# NOTE: pyml_trader uses --dry-run (inverted), others use --live
AGENTS = {
    "SafeAgent": {
        "module": "agents.application.pyml_trader",
        "args": [],  # No --dry-run = live mode (reads from bot_state.json)
        "restart_delay": 5,
    },
    "ScalperAgent": {
        "module": "agents.application.pyml_scalper",
        "args": ["--live"],
        "restart_delay": 3,
    },
    "CopyTrader": {
        "module": "agents.application.pyml_copy_trader",
        "args": ["--live"],
        "restart_delay": 5,
    },
    "SmartAgent": {
        "module": "agents.application.smart_trader",
        "args": ["--live"],
        "restart_delay": 10,
    },
    "SportsAgent": {
        "module": "agents.application.sports_trader",
        "args": ["--live"],
        "restart_delay": 10,
    },
    "EsportsAgent": {
        "module": "agents.application.esports_trader",
        "args": ["--live", "--growth"],
        "restart_delay": 10,
    },
}

# Staggered startup delays (seconds) to avoid API rate limits
STARTUP_DELAYS = {
    "SafeAgent": 0,
    "ScalperAgent": 2,
    "CopyTrader": 4,
    "SmartAgent": 6,
    "SportsAgent": 8,
    "EsportsAgent": 10,
}

MAX_RESTARTS = 5  # Max restarts per agent per hour
restart_counts = {name: [] for name in AGENTS}  # Track restart timestamps


def run_agent(name: str, module: str, args: list):
    """Run a single agent as subprocess."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting {name}...")
    cmd = ["python3", "-m", module] + args
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    env["PYTHONUNBUFFERED"] = "1"
    
    # Use Popen for non-blocking execution
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    
    # Stream output with agent prefix
    try:
        for line in proc.stdout:
            print(f"[{name}] {line.rstrip()}")
    except:
        pass
    
    proc.wait()
    return proc.returncode


def should_restart(name: str) -> bool:
    """Check if agent should be restarted (rate limit)."""
    now = time.time()
    hour_ago = now - 3600
    
    # Clean old entries
    restart_counts[name] = [t for t in restart_counts[name] if t > hour_ago]
    
    if len(restart_counts[name]) >= MAX_RESTARTS:
        print(f"⚠️ {name} hit restart limit ({MAX_RESTARTS}/hour). Pausing restarts.")
        return False
    
    restart_counts[name].append(now)
    return True


def agent_worker(name: str, config: dict):
    """Worker that runs agent and auto-restarts on crash."""
    while True:
        exit_code = run_agent(name, config["module"], config["args"])
        
        if exit_code == 0:
            print(f"[{name}] Exited cleanly (code 0). Not restarting.")
            break
        
        print(f"[{name}] Crashed with code {exit_code}.")
        
        if not should_restart(name):
            print(f"[{name}] Restart limit hit. Stopping worker.")
            break
        
        delay = config["restart_delay"]
        print(f"[{name}] Restarting in {delay}s...")
        time.sleep(delay)


def main():
    os.environ["PYTHONPATH"] = "."
    os.environ["PYTHONUNBUFFERED"] = "1"
    
    processes = {}
    shutdown_flag = False
    
    def signal_handler(sig, frame):
        nonlocal shutdown_flag
        print("\n🛑 Shutting down all agents...")
        shutdown_flag = True
        for name, p in processes.items():
            if p.is_alive():
                print(f"   Terminating {name}...")
                p.terminate()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Staggered startup
    print("=" * 60)
    print("🚀 POLYAGENT 5-AGENT ORCHESTRATOR")
    print("=" * 60)
    print(f"Agents: {', '.join(AGENTS.keys())}")
    print("=" * 60)
    
    for name, config in AGENTS.items():
        delay = STARTUP_DELAYS.get(name, 0)
        if delay > 0:
            print(f"⏳ Waiting {delay}s before starting {name}...")
            time.sleep(delay)
        
        p = multiprocessing.Process(
            target=agent_worker,
            args=(name, config),
            name=name,
        )
        p.start()
        processes[name] = p
        print(f"✅ {name} started (PID: {p.pid})")
    
    print("\n" + "=" * 60)
    print("🟢 All 5 agents running. Press Ctrl+C to stop.")
    print("=" * 60 + "\n")
    
    # Monitor loop
    while not shutdown_flag:
        time.sleep(30)
        
        dead_agents = []
        for name, p in processes.items():
            if not p.is_alive():
                dead_agents.append(name)
        
        if dead_agents:
            print(f"\n⚠️ Dead agents: {dead_agents}")
            # Workers handle their own restarts, so just log


if __name__ == "__main__":
    main()
