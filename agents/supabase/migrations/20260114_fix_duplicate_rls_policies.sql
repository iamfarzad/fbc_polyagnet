-- =============================================================================
-- Fix Multiple Permissive RLS Policies
-- This migration removes duplicate policies and consolidates them into single policies
-- =============================================================================

-- Drop ALL existing policies on affected tables dynamically
-- This ensures we catch all duplicates regardless of their names

DO $$
DECLARE
    r RECORD;
    tables TEXT[] := ARRAY['agent_state', 'trades', 'positions', 'chat_history', 'llm_activity', 'config'];
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY tables
    LOOP
        -- Drop all policies for this table
        FOR r IN 
            SELECT policyname 
            FROM pg_policies 
            WHERE schemaname = 'public' 
            AND tablename = table_name
        LOOP
            EXECUTE format('DROP POLICY IF EXISTS %I ON %I', r.policyname, table_name);
            RAISE NOTICE 'Dropped policy % on table %', r.policyname, table_name;
        END LOOP;
    END LOOP;
END $$;

-- Recreate single consolidated policies per table
-- For private dashboard: allow all operations for all roles
-- This is appropriate since you mentioned it's private with only you accessing it

CREATE POLICY "allow_all_operations_agent_state" ON agent_state
    FOR ALL
    USING (true)
    WITH CHECK (true);

CREATE POLICY "allow_all_operations_trades" ON trades
    FOR ALL
    USING (true)
    WITH CHECK (true);

CREATE POLICY "allow_all_operations_positions" ON positions
    FOR ALL
    USING (true)
    WITH CHECK (true);

CREATE POLICY "allow_all_operations_chat_history" ON chat_history
    FOR ALL
    USING (true)
    WITH CHECK (true);

CREATE POLICY "allow_all_operations_llm_activity" ON llm_activity
    FOR ALL
    USING (true)
    WITH CHECK (true);

CREATE POLICY "allow_all_operations_config" ON config
    FOR ALL
    USING (true)
    WITH CHECK (true);
