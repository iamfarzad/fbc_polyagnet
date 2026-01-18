# Esports Agent Diagnosis - Why Not Trading?

## Problem
- ✅ Agent is running and scanning (940 markets found)
- ✅ PandaScore API key is configured
- ❌ Agent is NOT trading despite live markets on Polymarket

## Root Cause Analysis

### Issue #1: Smart Polling Skipping Data API Calls

**Location:** `agents/application/esports_trader.py` lines 1464-1469

**Problem:**
- Smart polling logic skips PandaScore API calls if `time_since_last < poll_interval`
- Default poll interval: 45 seconds (Tier 2)
- If agent scans every 30s but polls every 45s, it skips most API calls
- Result: `live_matches = []` most of the time

**Code:**
```python
time_since_last = current_time - self.last_live_poll
should_poll = time_since_last >= poll_interval

if not should_poll:
    print(f"   ⏳ Smart Polling: Skipping Data API ({time_since_last:.1f}s / {poll_interval}s)")
    live_matches = [] # Skip call
```

**Impact:**
- Agent finds 940 markets but has no live match data
- `match_market_to_live_game()` returns None
- Falls through to PATH B (disabled market-based trading)
- Result: No trades executed

---

### Issue #2: Market Matching May Fail

**Location:** `agents/application/esports_trader.py` lines 998-1022

**Problem:**
- `match_market_to_live_game()` uses fuzzy string matching
- Team names from Polymarket may not match PandaScore team names exactly
- Example: "G2 Esports" vs "G2" vs "G2 Gaming"

**Code:**
```python
team1_match = market_team1 in live_team1 or live_team1 in market_team1
```

**Impact:**
- Even if PandaScore returns live matches, matching may fail
- No match = No trade (PATH A requires `live_match`)

---

### Issue #3: Edge Threshold Too High

**Location:** `agents/application/esports_trader.py` line 75

**Problem:**
- `MIN_EDGE_PERCENT = 1.5` (1.5% edge required)
- This is quite high for esports markets
- May filter out valid opportunities

**Impact:**
- Even with live data and matched games, edge may be < 1.5%
- Falls through to "Near Miss" logging (0.5% - 1.5%)
- No trade executed

---

### Issue #4: PATH B Disabled (Market-Based Trading)

**Location:** `agents/application/esports_trader.py` lines 1571-1595

**Problem:**
- Market-based trading (without PandaScore data) is disabled
- Code says: "Without Pandascore data, this is essentially gambling"
- Only arbitrage opportunities (< 0.985 spread) would execute

**Impact:**
- If PandaScore API fails or returns empty, no fallback trading
- Agent skips all markets

---

## Solutions

### Fix #1: Force Initial Poll + Better Logging

**Change:** Always poll on first scan, add better logging

```python
# Force poll on first scan (last_live_poll = 0)
if self.last_live_poll == 0:
    should_poll = True
    print(f"   🔄 First scan: Fetching PandaScore data...")

if not should_poll:
    print(f"   ⏳ Smart Polling: Skipping Data API ({time_since_last:.1f}s / {poll_interval}s)")
    live_matches = [] # Skip call
else:
    print(f"   📡 Fetching live match data from PandaScore...")
    # ... existing code
    print(f"   ✅ Found {len(live_matches)} live matches")
```

### Fix #2: Improve Market Matching

**Change:** Better fuzzy matching, handle team name variations

```python
def match_market_to_live_game(self, market, live_matches):
    # Normalize team names (remove "Esports", "Gaming", etc.)
    def normalize(name):
        return name.lower().replace(" esports", "").replace(" gaming", "").strip()
    
    market_team1 = normalize(market.team1)
    market_team2 = normalize(market.team2)
    
    # ... improved matching logic
```

### Fix #3: Lower Edge Threshold or Make Configurable

**Change:** Reduce MIN_EDGE_PERCENT or add dynamic threshold

```python
MIN_EDGE_PERCENT = 1.0  # Lower from 1.5% to 1.0%
# Or make it dynamic based on market conditions
```

### Fix #4: Enable Fallback Trading (Optional)

**Change:** Allow basic market-based trading when no PandaScore data

```python
# Instead of skipping all markets, allow arbitrage trades
if spread_sum < 0.985:  # True arbitrage
    # Execute trade
```

---

## Immediate Action Items

1. **Add logging** to see if PandaScore API is being called
2. **Check if live_matches is empty** - add log: "Found X live matches"
3. **Verify market matching** - log matched/unmatched markets
4. **Check edge calculations** - log edges found vs threshold

---

## Diagnostic Commands

```bash
# Check if PandaScore API is being called
fly logs --app polymarket-bots-farzad | grep -E "(found.*active games|PandaScore|live matches)"

# Check for market matching
fly logs --app polymarket-bots-farzad | grep -E "(TEEMU MODE|match_market|NO PANDASCORE DATA)"

# Check edge calculations
fly logs --app polymarket-bots-farzad | grep -E "(DATA EDGE|Edge|edge.*%|WAIT.*Edge)"
```
