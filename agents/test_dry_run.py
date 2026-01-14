#!/usr/bin/env python3
"""
Dry Run Test Suite - Test all agents and monitor performance/lag
"""
import os
import sys
import time
import signal
import subprocess
import multiprocessing
import json
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# Add parent path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

@dataclass
class AgentTestResult:
    """Results from testing an agent"""
    agent_name: str
    started: bool = False
    startup_time_ms: float = 0
    first_scan_time_ms: float = 0
    errors: List[str] = None
    warnings: List[str] = None
    last_activity: Optional[str] = None
    status: str = "not_started"  # not_started, running, error, timeout
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.warnings is None:
            self.warnings = []

class AgentMonitor:
    """Monitors an agent process and captures output"""
    
    def __init__(self, agent_name: str, command: List[str], timeout_seconds: int = 300):
        self.agent_name = agent_name
        self.command = command
        self.timeout = timeout_seconds
        self.process: Optional[subprocess.Popen] = None
        self.result = AgentTestResult(agent_name=agent_name)
        self.start_time = None
        self.output_lines = []
        
    def start(self):
        """Start the agent process"""
        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = "."
            env["PYTHONUNBUFFERED"] = "1"
            
            self.start_time = time.time()
            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
            self.result.started = True
            self.result.startup_time_ms = (time.time() - self.start_time) * 1000
            self.result.status = "running"
            return True
        except Exception as e:
            self.result.errors.append(f"Failed to start: {e}")
            self.result.status = "error"
            return False
    
    def monitor(self, duration_seconds: int = 60):
        """Monitor the process for a duration"""
        if not self.process:
            return
            
        first_scan_seen = False
        end_time = time.time() + duration_seconds
        
        while time.time() < end_time:
            if self.process.poll() is not None:
                # Process died
                self.result.status = "error"
                self.result.errors.append(f"Process exited with code {self.process.returncode}")
                break
                
            # Read output (non-blocking)
            try:
                line = self.process.stdout.readline()
                if line:
                    line = line.strip()
                    self.output_lines.append(line)
                    self.result.last_activity = line[:100]  # Truncate long lines
                    
                    # Detect first scan
                    if not first_scan_seen:
                        scan_keywords = ["scanning", "scan", "checking", "fetching", "discovering"]
                        if any(kw in line.lower() for kw in scan_keywords):
                            first_scan_seen = True
                            self.result.first_scan_time_ms = (time.time() - self.start_time) * 1000
                    
                    # Detect errors
                    if "error" in line.lower() or "exception" in line.lower() or "failed" in line.lower():
                        if "error" not in line.lower()[:20]:  # Avoid duplicate logging
                            self.result.errors.append(line)
                    
                    # Detect warnings
                    if "warning" in line.lower() or "warn" in line.lower():
                        self.result.warnings.append(line)
                        
            except Exception as e:
                pass
                
            time.sleep(0.1)  # Small sleep to avoid busy waiting
        
        # Check if still running
        if self.process.poll() is None:
            self.result.status = "running"
        else:
            self.result.status = "error"
    
    def stop(self):
        """Stop the agent process"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                try:
                    self.process.kill()
                except:
                    pass

def test_agent(agent_name: str, command: List[str], monitor_duration: int = 60) -> AgentTestResult:
    """Test a single agent"""
    print(f"\n{'='*60}")
    print(f"Testing: {agent_name}")
    print(f"{'='*60}")
    
    monitor = AgentMonitor(agent_name, command)
    
    if not monitor.start():
        print(f"❌ Failed to start {agent_name}")
        return monitor.result
    
    print(f"✅ Started {agent_name} (PID: {monitor.process.pid})")
    print(f"Monitoring for {monitor_duration} seconds...")
    
    try:
        monitor.monitor(duration_seconds=monitor_duration)
    except KeyboardInterrupt:
        print(f"\n⚠️  Interrupted {agent_name}")
    finally:
        monitor.stop()
        print(f"🛑 Stopped {agent_name}")
    
    return monitor.result

def main():
    """Run dry mode tests for all agents"""
    print("="*60)
    print("DRY RUN TEST SUITE")
    print("="*60)
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    # Check environment
    print("Environment Check:")
    print(f"  PYTHONPATH: {os.environ.get('PYTHONPATH', 'NOT SET')}")
    print(f"  Working Dir: {os.getcwd()}")
    
    # Check for Supabase
    has_supabase = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"))
    print(f"  Supabase: {'✅ Configured' if has_supabase else '⚠️  Not configured (will use local fallback)'}")
    
    # Check for API keys
    has_perplexity = bool(os.getenv("PERPLEXITY_API_KEY"))
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    print(f"  Perplexity API: {'✅' if has_perplexity else '❌'}")
    print(f"  OpenAI API: {'✅' if has_openai else '❌'}")
    print()
    
    # Define agents to test (correct module paths)
    agents = [
        {
            "name": "Safe Agent (pyml_trader)",
            "command": ["python3", "-m", "agents.application.pyml_trader", "--dry-run"]
        },
        {
            "name": "Scalper (pyml_scalper)",
            "command": ["python3", "-m", "agents.application.pyml_scalper"]
        },
        {
            "name": "Copy Trader",
            "command": ["python3", "-m", "agents.application.pyml_copy_trader"]
        },
        {
            "name": "Smart Trader",
            "command": ["python3", "-m", "agents.application.smart_trader"]
        },
        {
            "name": "Sports Trader",
            "command": ["python3", "-m", "agents.application.sports_trader"]
        },
        {
            "name": "Esports Trader",
            "command": ["python3", "-m", "agents.application.esports_trader"]
        },
    ]
    
    results = []
    
    # Test each agent sequentially (to avoid resource conflicts)
    for agent_config in agents:
        try:
            result = test_agent(
                agent_config["name"],
                agent_config["command"],
                monitor_duration=60  # Monitor for 60 seconds
            )
            results.append(result)
            
            # Brief pause between agents
            time.sleep(2)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Test interrupted by user")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error testing {agent_config['name']}: {e}")
            results.append(AgentTestResult(
                agent_name=agent_config["name"],
                status="error",
                errors=[str(e)]
            ))
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for result in results:
        print(f"\n{result.agent_name}:")
        print(f"  Status: {result.status.upper()}")
        print(f"  Started: {'✅' if result.started else '❌'}")
        if result.startup_time_ms > 0:
            print(f"  Startup Time: {result.startup_time_ms:.0f}ms")
        if result.first_scan_time_ms > 0:
            print(f"  First Scan: {result.first_scan_time_ms:.0f}ms")
        else:
            print(f"  First Scan: ⚠️  Not detected (may be slow or no activity)")
        
        if result.errors:
            print(f"  Errors: {len(result.errors)}")
            for err in result.errors[:3]:  # Show first 3 errors
                print(f"    - {err[:80]}")
        
        if result.warnings:
            print(f"  Warnings: {len(result.warnings)}")
            for warn in result.warnings[:3]:  # Show first 3 warnings
                print(f"    - {warn[:80]}")
        
        if result.last_activity:
            print(f"  Last Activity: {result.last_activity[:60]}...")
    
    # Performance analysis
    print("\n" + "="*60)
    print("PERFORMANCE ANALYSIS")
    print("="*60)
    
    successful_agents = [r for r in results if r.started and r.status == "running"]
    slow_agents = [r for r in results if r.first_scan_time_ms > 30000]  # >30s
    fast_agents = [r for r in results if r.first_scan_time_ms > 0 and r.first_scan_time_ms < 5000]  # <5s
    
    print(f"\n✅ Successful Agents: {len(successful_agents)}/{len(results)}")
    print(f"⚡ Fast Agents (<5s first scan): {len(fast_agents)}")
    print(f"🐌 Slow Agents (>30s first scan): {len(slow_agents)}")
    
    if slow_agents:
        print("\n⚠️  SLOW AGENTS (may need optimization):")
        for agent in slow_agents:
            print(f"  - {agent.agent_name}: {agent.first_scan_time_ms/1000:.1f}s")
    
    # Save results to JSON
    output_file = "dry_run_test_results.json"
    with open(output_file, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    
    print(f"\n📄 Full results saved to: {output_file}")
    print(f"\nCompleted at: {datetime.now().isoformat()}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test suite interrupted")
        sys.exit(1)
