import multiprocessing
import os
import signal
import sys
import time
import subprocess


def run_safe_agent():
    print("Starting Safe Agent...")
    subprocess.run(["python3", "-m", "agents.application.pyml_trader"], env=os.environ.copy())


def run_scalper_agent():
    print("Starting Scalper Agent...")
    subprocess.run(["python3", "-m", "agents.application.pyml_scalper", "--live"], env=os.environ.copy())


def run_copy_trader():
    print("Starting Copy Trader...")
    subprocess.run(["python3", "-m", "agents.application.pyml_copy_trader"], env=os.environ.copy())


if __name__ == "__main__":
    os.environ["PYTHONPATH"] = "."
    os.environ["PYTHONUNBUFFERED"] = "1"
    
    processes = []
    
    p_safe = multiprocessing.Process(target=run_safe_agent, name="SafeAgent")
    p_scalper = multiprocessing.Process(target=run_scalper_agent, name="ScalperAgent")
    p_copy = multiprocessing.Process(target=run_copy_trader, name="CopyTrader")
    
    processes.append(p_safe)
    processes.append(p_scalper)
    processes.append(p_copy)
    
    for p in processes:
        p.start()
        
    def signal_handler(sig, frame):
        print("Shutting down everything...")
        for p in processes:
            p.terminate()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("Bot Orchestrator is running (Safe + Scalper + CopyTrader).")
    
    while True:
        time.sleep(10)
        for p in processes:
            if not p.is_alive():
                print(f"Warning: {p.name} died.")
