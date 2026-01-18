# Connection Checklist: Fly ↔ Supabase ↔ Vercel

## Connection Point Status

### 1. Fly → Supabase

**Status:** 🟡 **PARTIAL** - Can read, but not writing LLM activity

**Current State:**
- ✅ **SUPABASE_SERVICE_ROLE_KEY** is set in Fly secrets: `272d3de36540b1ee`
- ✅ **SUPABASE_URL** is set: `e4dbf20b6afcfeea`
- ✅ Can successfully read `agent_state` table (200 OK responses in logs)
- ❌ No LLM activity logs appearing in Fly.io logs
- ❌ No "📝 LLM activity logged" messages found

**Verification:**
```bash
# Check secrets
fly secrets list --app polymarket-bots-farzad | grep SUPABASE
# Result: All 4 Supabase secrets present

# Check logs for LLM activity
fly logs --app polymarket-bots-farzad --no-tail | grep "📝"
# Result: No logs found
```

**Code Analysis:**
- `agents/utils/supabase_client.py` has `log_llm_activity` method with SDK + REST fallback
- `agents/application/esports_trader.py` line 1379 calls `supa.log_llm_activity()` for heartbeat
- `agents/application/sports_trader.py` line 649 also calls heartbeat logging

**Possible Issues:**
1. **SDK client not initialized** - If `self.client` is None, it falls back to REST
2. **REST fallback failing silently** - May be hitting errors but not logging them
3. **Agents not calling log_llm_activity** - Fast Mode may be bypassing LLM calls
4. **RLS policies blocking writes** - Row Level Security may be preventing inserts

**Recommendations:**
1. ✅ Secrets are configured correctly
2. Add more verbose logging to `log_llm_activity` to see what's happening
3. Test direct REST API call to Supabase from Fly.io to verify write permissions
4. Check Supabase RLS policies allow inserts on `llm_activity` table
5. Verify agents are actually calling `log_llm_activity` (may be bypassed in Fast Mode)

**Test Command:**
```bash
# Test if REST fallback works
fly ssh console -a polymarket-bots-farzad
python3 -c "
from agents.utils.supabase_client import get_supabase_state
supa = get_supabase_state()
print(f'URL: {supa.url}')
print(f'Key present: {bool(supa.key)}')
print(f'Use local fallback: {supa.use_local_fallback}')
print(f'Client initialized: {bool(supa.client)}')
result = supa.log_llm_activity(
    agent='test',
    action_type='test',
    market_question='Test',
    prompt_summary='Test',
    reasoning='Test',
    conclusion='TEST',
    confidence=1.0
)
print(f'Log result: {result}')
"
```

**Key Finding:**
- Code should log "✅ Supabase REST API configured" on init, but no such logs found
- This suggests either:
  1. Logs are filtered/not showing initialization
  2. Supabase client initialization happens before logging is set up
  3. Environment variables not being read correctly at runtime

---

### 2. Vercel → Supabase

**Status:** ❓ **UNKNOWN** - Cannot verify via API

**Expected Configuration:**
- Frontend code does NOT directly connect to Supabase
- All data flows through Fly.io API (`/api/llm-activity` endpoint)
- No `NEXT_PUBLIC_SUPABASE_URL` needed in frontend

**Code Analysis:**
- `dashboard-frontend/lib/api-url.ts` - Only uses `NEXT_PUBLIC_API_URL` or `NEXT_PUBLIC_FLY_API_URL`
- `dashboard-frontend/components/llm-terminal.tsx` - Fetches from Fly API, not Supabase
- No Supabase client imports found in frontend code

**Verification Required:**
1. Go to Vercel Dashboard → Project `fbc-polyagnet` → Settings → Environment Variables
2. Check if `NEXT_PUBLIC_API_URL` or `NEXT_PUBLIC_FLY_API_URL` is set
3. Should be: `https://polymarket-bots-farzad.fly.dev`

**Note:** Since frontend doesn't connect directly to Supabase, `NEXT_PUBLIC_SUPABASE_URL` is NOT needed. The frontend gets all data through the Fly.io API.

---

### 3. Vercel → Fly (API)

**Status:** ❓ **UNKNOWN** - Cannot verify via API

**Expected Configuration:**
- `NEXT_PUBLIC_API_URL` or `NEXT_PUBLIC_FLY_API_URL` → `https://polymarket-bots-farzad.fly.dev`
- Frontend uses this for:
  - REST API calls: `/api/dashboard`, `/api/llm-activity`, etc.
  - WebSocket connections: `wss://polymarket-bots-farzad.fly.dev/ws/dashboard`, `/ws/llm-activity`

**Code Analysis:**
```typescript
// dashboard-frontend/lib/api-url.ts
export function getApiUrl() {
  const url =
    process.env.NEXT_PUBLIC_API_URL ||
    process.env.NEXT_PUBLIC_FLY_API_URL ||
    "https://polymarket-bots-farzad.fly.dev"  // Fallback
  return url.replace(/\/$/, "")
}

export function getWsUrl() {
  const apiUrl = getApiUrl()
  const wsUrl = apiUrl.replace(/^http(s)?:\/\//, (m) => (m === "https://" ? "wss://" : "ws://"))
  return wsUrl
}
```

**Fallback Behavior:**
- If env vars not set, defaults to `https://polymarket-bots-farzad.fly.dev`
- This means connection should work even without env vars
- But explicit setting is recommended for clarity

**Verification Required:**
1. Go to Vercel Dashboard → Project `fbc-polyagnet` → Settings → Environment Variables
2. Check if `NEXT_PUBLIC_API_URL` or `NEXT_PUBLIC_FLY_API_URL` exists
3. If not set, frontend will use fallback (should still work)

**Test from Browser Console:**
```javascript
// On deployed Vercel page, open console and run:
fetch('/api/dashboard').then(r => r.json()).then(console.log)
// Should return dashboard data if connection works
```

---

## Summary & Action Items

### ✅ Verified
1. **Fly → Supabase Secrets:** All 4 secrets present and configured
2. **Fly → Supabase Reads:** Successfully reading `agent_state` table
3. **Vercel Build:** Deployment successful, no build errors
4. **Frontend Code:** Correctly configured to use Fly API

### ❓ Needs Manual Verification
1. **Vercel Environment Variables:**
   - Check `NEXT_PUBLIC_API_URL` or `NEXT_PUBLIC_FLY_API_URL`
   - Should be: `https://polymarket-bots-farzad.fly.dev`
   - Note: Has fallback, so may work without explicit setting

### 🟡 Issues Found
1. **Fly → Supabase Writes:**
   - Secrets configured ✅
   - Can read ✅
   - Cannot verify writes (no logs showing LLM activity)
   - Possible causes:
     - Agents not calling `log_llm_activity` (Fast Mode bypass)
     - SDK client not initialized
     - REST fallback failing silently
     - RLS policies blocking writes

### 🔧 Recommended Fixes

**Priority 1: Fix Fly → Supabase LLM Activity Logging**
```python
# Add verbose logging to agents/utils/supabase_client.py
def log_llm_activity(...):
    logger.info(f"Attempting to log LLM activity for {agent}")
    if self.client:
        logger.info("SDK client available")
    else:
        logger.warning("SDK client not available, using REST")
    if self.use_local_fallback:
        logger.warning("Using local fallback - Supabase not configured")
    # ... rest of method
```

**Priority 2: Verify Vercel Environment Variables**
- Access Vercel Dashboard manually
- Check Environment Variables section
- Verify `NEXT_PUBLIC_API_URL` or `NEXT_PUBLIC_FLY_API_URL` is set

**Priority 3: Test Supabase Write Permissions**
- Test direct REST API call from Fly.io
- Verify RLS policies allow inserts
- Check Supabase logs for failed insert attempts

---

## Connection Flow Diagram

```
┌─────────┐         ┌──────────┐         ┌─────────┐
│  Vercel │ ──────> │   Fly    │ ──────> │ Supabase│
│ Frontend│  HTTP   │   API    │  REST   │   DB    │
└─────────┘         └──────────┘         └─────────┘
     │                    │                    │
     │                    │                    │
     └────────────────────┴────────────────────┘
              WebSocket (dashboard, llm-activity)
```

**Data Flow:**
1. Vercel frontend → Fly API (REST + WebSocket)
2. Fly API → Supabase (reads `agent_state`, should write `llm_activity`)
3. Fly Agents → Supabase (direct REST calls for state management)

**Current Status:**
- ✅ Vercel → Fly: Working (with fallback)
- ✅ Fly → Supabase (Reads): Working
- 🟡 Fly → Supabase (Writes): Unknown (no logs)
