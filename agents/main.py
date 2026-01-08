import multiprocessing
import os
import signal
import sys
import time
import subprocess

def run_safe_agent():
    print("Starting Safe Agent...")
    # Using python -m for module resolution consistency
    subprocess.run(["python3", "-m", "agents.application.pyml_trader"], env=os.environ.copy())

def run_scalper_agent():
    print("Starting Scalper Agent...")
    subprocess.run(["python3", "pyml_ws_scalper.py", "--live"], env=os.environ.copy())

def run_dashboard():
    print("Starting Dashboard...")
    subprocess.run(["python3", "dashboard.py"], env=os.environ.copy())

if __name__ == "__main__":
    # Ensure all processes have access to the same environment
    os.environ["PYTHONPATH"] = "."
    os.environ["PYTHONUNBUFFERED"] = "1"
    
    processes = []
    
    p_safe = multiprocessing.Process(target=run_safe_agent, name="SafeAgent")
    p_scalper = multiprocessing.Process(target=run_scalper_agent, name="ScalperAgent")
    p_dash = multiprocessing.Process(target=run_dashboard, name="Dashboard")
    
    processes.append(p_safe)
    processes.append(p_scalper)
    processes.append(p_dash)
    
    for p in processes:
        p.start()
        
    def signal_handler(sig, frame):
        print("Shutting down everything...")
        for p in processes:
            p.terminate()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("Monolithic Bot Orchestrator is running.")
    
    # Keep main process alive
    while True:
        time.sleep(10)
        for p in processes:
            if not p.is_alive():
                print(f"Warning: {p.name} died. Restarting...")
                # We could implement restart logic here if desired
                # For now, let's just log it.
