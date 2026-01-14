#!/usr/bin/env python3
"""
Quick dry run test - runs each agent briefly and shows what's working/lagging
"""
import os
import sys
import subprocess
import signal
import time
from datetime import datetime

# Set environment
os.environ["PYTHONPATH"] = "."
os.environ["PYTHONUNBUFFERED"] = "1"

agents = [
    ("Safe Agent", ["python3", "-m", "agents.application.pyml_trader", "--dry-run"]),
    ("Scalper", ["python3", "-m", "agents.application.pyml_scalper"]),
    ("Copy Trader", ["python3", "-m", "agents.application.pyml_copy_trader"]),
    ("Smart Trader", ["python3", "-m", "agents.application.smart_trader"]),
    ("Sports Trader", ["python3", "-m", "agents.application.sports_trader"]),
    ("Esports Trader", ["python3", "-m", "agents.application.esports_trader"]),
]

def test_agent(name, cmd, duration=20):
    """Test an agent for a short duration"""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}")
    print(f"Duration: {duration}s")
    print("-" * 60)
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy()
        )
        
        start_time = time.time()
        output_lines = []
        first_activity = None
        errors = []
        
        # Monitor for duration
        while time.time() - start_time < duration:
            if proc.poll() is not None:
                # Process exited
                remaining_output = proc.stdout.read()
                if remaining_output:
                    output_lines.extend(remaining_output.split('\n'))
                break
            
            # Read line (non-blocking)
            line = proc.stdout.readline()
            if line:
                line = line.strip()
                output_lines.append(line)
                
                if not first_activity and line:
                    first_activity = line
                    elapsed = time.time() - start_time
                    print(f"✅ First output after {elapsed:.1f}s: {line[:80]}")
                
                # Print important lines
                if any(keyword in line.lower() for keyword in ["error", "exception", "failed", "scanning", "found", "trade", "market"]):
                    print(f"  {line[:100]}")
                
                if "error" in line.lower() or "exception" in line.lower():
                    errors.append(line)
            
            time.sleep(0.1)
        
        # Kill process
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except:
            try:
                proc.kill()
            except:
                pass
        
        elapsed = time.time() - start_time
        
        # Summary
        print(f"\n📊 Summary:")
        print(f"  Runtime: {elapsed:.1f}s")
        print(f"  Output lines: {len(output_lines)}")
        print(f"  Errors: {len(errors)}")
        
        if errors:
            print(f"  ⚠️  Errors found:")
            for err in errors[:3]:
                print(f"    - {err[:80]}")
        
        if not first_activity:
            print(f"  ⚠️  No output detected (may be slow to start)")
        
        return {
            "name": name,
            "success": proc.returncode == 0 or proc.returncode is None,
            "output_lines": len(output_lines),
            "errors": len(errors),
            "first_activity_time": elapsed if first_activity else None
        }
        
    except KeyboardInterrupt:
        print(f"\n⚠️  Interrupted")
        if proc:
            proc.terminate()
        raise
    except Exception as e:
        print(f"❌ Failed to test {name}: {e}")
        return {
            "name": name,
            "success": False,
            "error": str(e)
        }

def main():
    print("="*60)
    print("DRY RUN TEST SUITE")
    print("="*60)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check environment
    print("Environment:")
    print(f"  PYTHONPATH: {os.environ.get('PYTHONPATH', 'NOT SET')}")
    print(f"  Working Dir: {os.getcwd()}")
    
    has_supabase = bool(os.getenv("SUPABASE_URL"))
    has_perplexity = bool(os.getenv("PERPLEXITY_API_KEY"))
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    
    print(f"  Supabase: {'✅' if has_supabase else '❌'}")
    print(f"  Perplexity: {'✅' if has_perplexity else '❌'}")
    print(f"  OpenAI: {'✅' if has_openai else '❌'}")
    print()
    
    results = []
    
    try:
        for name, cmd in agents:
            result = test_agent(name, cmd, duration=20)
            results.append(result)
            time.sleep(1)  # Brief pause between agents
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    
    # Final summary
    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    
    working = [r for r in results if r.get("success") and r.get("output_lines", 0) > 0]
    slow = [r for r in results if r.get("first_activity_time", 0) and r.get("first_activity_time", 0) > 10]
    errors = [r for r in results if r.get("errors", 0) > 0]
    
    print(f"\n✅ Working Agents: {len(working)}/{len(results)}")
    for r in working:
        print(f"  - {r['name']}: {r.get('output_lines', 0)} lines output")
    
    if slow:
        print(f"\n🐌 Slow Agents (>10s first activity):")
        for r in slow:
            print(f"  - {r['name']}: {r.get('first_activity_time', 0):.1f}s")
    
    if errors:
        print(f"\n⚠️  Agents with Errors:")
        for r in errors:
            print(f"  - {r['name']}: {r.get('errors', 0)} errors")
    
    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
