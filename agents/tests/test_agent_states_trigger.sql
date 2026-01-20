-- =============================================================================
-- TEST SCRIPT: Validate agent_states_set_last_updated Trigger
-- Run this in Supabase SQL Editor
-- =============================================================================

BEGIN;

-- 1. Insert a new record
INSERT INTO public.agent_states (agent_name, state, metadata)
VALUES ('test_trigger_agent', 'initial_state', '{"test": true}'::jsonb)
RETURNING id, agent_name, last_updated;

-- 2. Wait a moment (simulated)
-- In real SQL execution, we can't easily "sleep" without pg_sleep, 
-- but we can verify the update mechanism.

-- 3. Update the record
UPDATE public.agent_states
SET state = 'updated_state', metadata = '{"test": false}'::jsonb
WHERE agent_name = 'test_trigger_agent'
RETURNING id, agent_name, last_updated;

-- 4. Verify that last_updated changed (manual check required if running interactively)
-- Or we can auto-verify in a block:
DO $$
DECLARE
    r_id uuid;
    t1 timestamptz;
    t2 timestamptz;
BEGIN
    -- Insert
    INSERT INTO public.agent_states (agent_name, state)
    VALUES ('auto_test_agent', 'init')
    RETURNING id, last_updated INTO r_id, t1;
    
    PERFORM pg_sleep(1); -- Sleep 1s to ensure timestamp diff
    
    -- Update
    UPDATE public.agent_states
    SET state = 'mod'
    WHERE id = r_id
    RETURNING last_updated INTO t2;
    
    IF t2 > t1 THEN
        RAISE NOTICE '✅ SUCCESS: Trigger updated timestamp (T1: %, T2: %)', t1, t2;
    ELSE
        RAISE EXCEPTION '❌ FAILURE: Timestamp did not update (T1: %, T2: %)', t1, t2;
    END IF;
    
    -- Cleanup
    DELETE FROM public.agent_states WHERE id = r_id;
    DELETE FROM public.agent_states WHERE agent_name = 'test_trigger_agent';
END $$;

COMMIT;
