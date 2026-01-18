# Will the Esports Agent Start Trading?

## ✅ Configuration Status

**Agent Mode:** 🔴 **LIVE TRADING** (not dry_run)
- Started with `--live` flag in `fly.toml`
- Code: `dry_run=not is_live` → `dry_run=False`

**PandaScore API:** ✅ Configured
- API key is set in Fly secrets
- Current usage: 120/1000 (12%)

**Recent Fixes:** ✅ Applied
- API call counting fixed (now counts 3 calls for get_all_live_matches)
- Initial poll forced (will fetch data on first scan)
- Better logging added (will show why trades aren't executing)

---

## 🔄 Trading Flow (What Must Happen)

### Step 1: Fetch Live Matches ✅
**Status:** Should work now (initial poll forced)
- Calls PandaScore API for LoL, CS2, Valorant
- Returns list of live matches

**Check logs for:**
```
✅ Found X live matches in data feed
📊 API Usage: X/1000 (X.X%)
```

### Step 2: Match Markets to Live Games ⚠️
**Status:** Depends on team name matching
- Agent finds 940 markets on Polymarket
- Must match team names from Polymarket to PandaScore
- Uses fuzzy string matching

**Check logs for:**
```
✅ Matched: Team1 vs Team2 -> Live match found
```

**If no matches:**
```
⚠️ No markets matched to live games - check team name matching
```

### Step 3: Fetch Match State ⚠️
**Status:** Requires API calls (counted correctly now)
- Fetches detailed game stats (gold, kills, etc.)
- LoL: 2 API calls (match + game details)
- CS2/Valorant: 1 API call

**Check logs for:**
```
📡 Fetched match state for {match_id} (LOL, 2 API calls)
💾 Using cached match state for {match_id}
```

### Step 4: Calculate Edge ⚠️
**Status:** Requires edge > 1.5%
- Compares true probability (from game stats) vs market odds
- Edge = true_prob - market_prob
- **Must be > 1.5%** to trade

**Check logs for:**
```
📊 Edge Analysis: Market question...
   True Prob: X.X% | Market: X.X% | Edge: +X.X% | Threshold: 1.5%
🔥 DATA EDGE DETECTED: YES/NO (Edge: X.X% > 1.5%)
```

**If edge too small:**
```
WAIT (Edge too small)
```

### Step 5: Execute Trade ✅
**Status:** Should execute if all above pass
- Checks for open orders (prevents duplicates)
- Calculates bet size (Kelly criterion)
- Checks liquidity depth
- Places limit order

**Check logs for:**
```
🎯 TRADE: YES/NO on Team1 vs Team2
   Our Prob: X.X% | Market: X.X% | Edge: +X.X%
   Entry: $X.XXX | Size: $X.XX | Shares: X.X
✅ FILLED!
```

---

## 🚨 Potential Blockers

### Blocker #1: No Live Matches Found
**Symptom:** `Found 0 live matches in data feed`
**Causes:**
- No games currently live
- PandaScore API error
- Rate limiting (429 errors)

**Fix:** Check PandaScore API status, wait for live games

### Blocker #2: Markets Don't Match Live Games
**Symptom:** `No markets matched to live games`
**Causes:**
- Team name mismatch (e.g., "G2 Esports" vs "G2")
- Different game types
- Markets for upcoming games, not live

**Fix:** Improve team name matching algorithm

### Blocker #3: Edge Too Small
**Symptom:** `Edge: +0.8% < Target 1.5%`
**Causes:**
- Market odds are efficient (already priced correctly)
- Game stats don't show clear advantage
- MIN_EDGE_PERCENT threshold too high

**Fix:** Lower MIN_EDGE_PERCENT or wait for better opportunities

### Blocker #4: Insufficient Balance
**Symptom:** `Insufficient esports allocation: $X.XX (need $5.00)`
**Causes:**
- Balance < $12.50 (40% allocation < $5)
- All funds in other positions

**Fix:** Increase balance or reduce MIN_BET_USD

### Blocker #5: Liquidity Too Low
**Symptom:** `Bet size too small after liquidity cap: $X.XX`
**Causes:**
- Order book depth < $33 (15% cap)
- Market is illiquid

**Fix:** Skip illiquid markets (already handled)

---

## 📊 What to Check After Deployment

### 1. Check Agent Mode
```bash
fly logs --app polymarket-bots-farzad | grep -E "(Mode:|DRY RUN|LIVE TRADING)"
```
**Expected:** `Mode: 🔴 LIVE TRADING`

### 2. Check PandaScore Data Fetching
```bash
fly logs --app polymarket-bots-farzad | grep -E "(✅ Found.*live matches|📊 API Usage)"
```
**Expected:** `✅ Found X live matches` (X > 0)

### 3. Check Market Matching
```bash
fly logs --app polymarket-bots-farzad | grep -E "(✅ Matched|Scan Summary)"
```
**Expected:** `✅ Matched: Team1 vs Team2` or scan summary showing matched_count > 0

### 4. Check Edge Calculations
```bash
fly logs --app polymarket-bots-farzad | grep -E "(📊 Edge Analysis|🔥 DATA EDGE|WAIT.*Edge)"
```
**Expected:** Edge calculations showing edges found

### 5. Check Trade Execution
```bash
fly logs --app polymarket-bots-farzad | grep -E "(🎯 TRADE|✅ FILLED)"
```
**Expected:** Trade logs when edge > 1.5% found

---

## 🎯 Expected Behavior

### Scenario 1: Everything Works ✅
1. Agent fetches live matches → Finds 5-10 live games
2. Matches markets → Matches 2-3 markets to live games
3. Calculates edges → Finds 1-2 edges > 1.5%
4. Executes trades → Places limit orders
5. **Result:** Trades execute within minutes

### Scenario 2: No Live Games ⏸️
1. Agent fetches live matches → Finds 0 live games
2. **Result:** No trading (correct behavior)
3. **Action:** Wait for live games or check PandaScore API

### Scenario 3: No Matches ⚠️
1. Agent finds live games → Finds 5-10 games
2. Markets don't match → Team names don't align
3. **Result:** No trading
4. **Action:** Improve team name matching algorithm

### Scenario 4: No Edge ⚠️
1. Agent matches markets → Matches found
2. Edge calculations → All edges < 1.5%
3. **Result:** No trading (waiting for better opportunities)
4. **Action:** Lower MIN_EDGE_PERCENT or wait

---

## ✅ Summary

**Will it trade?** **YES, IF:**
1. ✅ PandaScore API returns live matches (should work now)
2. ⚠️ Markets match to live games (depends on team names)
3. ⚠️ Edge > 1.5% found (depends on market efficiency)
4. ✅ Balance sufficient (check current balance)
5. ✅ Liquidity sufficient (most markets should be fine)

**Most Likely Outcome:**
- Agent will start fetching data correctly ✅
- May find matches and calculate edges ⚠️
- May not trade immediately if edges are small ⚠️
- Will trade when edge > 1.5% is found ✅

**Next Steps:**
1. Monitor logs after deployment
2. Check scan summary for matched/analyzed counts
3. Review edge calculations
4. Adjust MIN_EDGE_PERCENT if needed (currently 1.5%)
