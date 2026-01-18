# Fix Duplicate RLS Policies

## Problem
Multiple permissive RLS policies exist for the same role/action combinations on these tables:
- `agent_state`
- `trades`
- `positions`
- `chat_history`
- `llm_activity`
- `config`

This causes performance issues as each policy must be executed for every query.

## Solution
Run the migration SQL to drop all duplicate policies and recreate single consolidated policies.

## Migration File
Location: `agents/supabase/migrations/20260114_fix_duplicate_rls_policies.sql`

## How to Run

### Option 1: Supabase Dashboard (Recommended)
1. Go to: https://supabase.com/dashboard/project/thxejjhpnzzigjcvizxl/sql/new
2. Copy and paste the contents of `agents/supabase/migrations/20260114_fix_duplicate_rls_policies.sql`
3. Click "Run" to execute

### Option 2: Supabase CLI (if you have DB password)
```bash
cd /Users/farzad/polyagent
supabase db push
```

### Option 3: Direct psql (if you have connection string)
```bash
psql "postgresql://postgres.thxejjhpnzzigjcvizxl:[PASSWORD]@aws-1-eu-north-1.pooler.supabase.com:6543/postgres" -f agents/supabase/migrations/20260114_fix_duplicate_rls_policies.sql
```

## What the Migration Does

1. **Drops all existing policies** on the affected tables dynamically (catches all duplicates)
2. **Recreates single consolidated policies** using `FOR ALL` with `USING (true)` and `WITH CHECK (true)`

This ensures:
- Only one policy per table
- Covers all operations (SELECT, INSERT, UPDATE, DELETE) for your private dashboard
- Applies to all roles (since it's private and only you access it)
- Better performance (single policy evaluation instead of multiple)

## Verification

After running the migration, verify in Supabase Dashboard:
1. Go to: Authentication > Policies
2. Check each table - you should see only ONE policy per table named:
   - `allow_all_operations_agent_state`
   - `allow_all_operations_trades`
   - `allow_all_operations_positions`
   - `allow_all_operations_chat_history`
   - `allow_all_operations_llm_activity`
   - `allow_all_operations_config`
