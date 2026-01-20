-- =============================================================================
-- POLYAGENT SUPABASE SCHEMA
-- Run this in Supabase SQL Editor or via CLI: supabase db push
-- =============================================================================

-- Agent State Table (shared state for dashboard toggles)
CREATE TABLE IF NOT EXISTS agent_state (
    id SERIAL PRIMARY KEY,
    agent_name TEXT UNIQUE NOT NULL,
    is_running BOOLEAN DEFAULT true,
    is_dry_run BOOLEAN DEFAULT true,
    last_activity TEXT,
    last_endpoint TEXT,
    heartbeat TIMESTAMPTZ DEFAULT NOW(),
    config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default state for all agents
INSERT INTO agent_state (agent_name, is_running, is_dry_run) VALUES
    ('safe', true, false),
    ('scalper', true, false),
    ('copy', true, false),
    ('smart', true, false),
    ('esports', true, false),
    ('sport', true, false)
ON CONFLICT (agent_name) DO NOTHING;

-- Trade History Table (persistent trade log)
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    agent TEXT NOT NULL,
    market_id TEXT,
    market_question TEXT,
    outcome TEXT,
    side TEXT,  -- BUY or SELL
    size_usd DECIMAL(10,4),
    price DECIMAL(6,4),
    token_id TEXT,
    status TEXT DEFAULT 'pending',  -- pending, filled, failed, closed
    pnl DECIMAL(10,4) DEFAULT 0,
    entry_time TIMESTAMPTZ DEFAULT NOW(),
    exit_time TIMESTAMPTZ,
    exit_price DECIMAL(6,4),
    reasoning TEXT,
    lesson_analyzed BOOLEAN DEFAULT NULL,  -- NULL = not analyzed, TRUE = lesson extracted
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_trades_agent ON trades(agent);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at DESC);

-- Positions Table (current open positions)
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    agent TEXT NOT NULL,
    market_id TEXT UNIQUE,
    market_question TEXT,
    outcome TEXT,
    entry_price DECIMAL(6,4),
    size_shares DECIMAL(12,4),
    size_usd DECIMAL(10,4),
    token_id TEXT,
    current_price DECIMAL(6,4),
    unrealized_pnl DECIMAL(10,4) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_positions_agent ON positions(agent);

-- Chat History Table (FBP agent conversations)
CREATE TABLE IF NOT EXISTS chat_history (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_history(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_history(created_at DESC);

-- LLM Activity Log (for transparency)
CREATE TABLE IF NOT EXISTS llm_activity (
    id SERIAL PRIMARY KEY,
    agent TEXT NOT NULL,
    action_type TEXT,  -- 'validate', 'discover', 'analyze'
    market_question TEXT,
    prompt_summary TEXT,
    reasoning TEXT,
    conclusion TEXT,
    confidence DECIMAL(4,2),
    data_sources TEXT[],
    tokens_used INTEGER DEFAULT 0,
    cost_usd DECIMAL(8,6) DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_agent ON llm_activity(agent);
CREATE INDEX IF NOT EXISTS idx_llm_created ON llm_activity(created_at DESC);

-- Lessons Learned Table (agent self-learning system)
CREATE TABLE IF NOT EXISTS lessons_learned (
    id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    market_question TEXT,
    original_reasoning TEXT,
    predicted_outcome TEXT,
    actual_outcome TEXT,
    pnl DECIMAL(10,4),
    mistake_type TEXT,  -- false_positive, false_negative, sizing, timing, none
    lesson_learned TEXT,
    trade_id INTEGER REFERENCES trades(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lessons_agent ON lessons_learned(agent);
CREATE INDEX IF NOT EXISTS idx_lessons_type ON lessons_learned(mistake_type);
CREATE INDEX IF NOT EXISTS idx_lessons_created ON lessons_learned(created_at DESC);

-- Global Config Table
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default config
INSERT INTO config (key, value) VALUES
    ('max_bet_usd', '2.0'),
    ('global_dry_run', 'false'),
    ('allocation', '{"safe": 0.1, "scalper": 0.8, "copy": 0.1}')
ON CONFLICT (key) DO NOTHING;

-- Enable Row Level Security (optional, for future auth)
ALTER TABLE agent_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE config ENABLE ROW LEVEL SECURITY;

-- Create policies to allow all operations (adjust for production)
CREATE POLICY "Allow all operations on agent_state" ON agent_state FOR ALL USING (true);
CREATE POLICY "Allow all operations on trades" ON trades FOR ALL USING (true);
CREATE POLICY "Allow all operations on positions" ON positions FOR ALL USING (true);
CREATE POLICY "Allow all operations on chat_history" ON chat_history FOR ALL USING (true);
CREATE POLICY "Allow all operations on llm_activity" ON llm_activity FOR ALL USING (true);
CREATE POLICY "Allow all operations on config" ON config FOR ALL USING (true);

-- Function to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for auto-updating timestamps
CREATE TRIGGER agent_state_updated_at
    BEFORE UPDATE ON agent_state
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER positions_updated_at
    BEFORE UPDATE ON positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Portfolio Snapshots (for historical graphs)
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    balance DECIMAL(10,4),
    equity DECIMAL(10,4),
    unrealized_pnl DECIMAL(10,4),
    cost_basis DECIMAL(10,4),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_snapshots_time ON portfolio_snapshots(timestamp DESC);

-- RLS for snapshots
ALTER TABLE portfolio_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all operations on portfolio_snapshots" ON portfolio_snapshots FOR ALL USING (true);

-- =============================================================================
-- NEW AGENT STATE SYSTEM (v2)
-- Added by user interaction on 2026-01-20
-- =============================================================================

-- Create base table public.agent_states
CREATE TABLE IF NOT EXISTS public.agent_states (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name text NOT NULL,
  state text NOT NULL,
  metadata jsonb DEFAULT '{}'::jsonb,
  last_updated timestamptz NOT NULL DEFAULT now()
);

-- Create view
CREATE OR REPLACE VIEW public.agent_state_view AS
SELECT
  id,
  agent_name,
  state,
  metadata,
  last_updated
FROM public.agent_states;

-- Create materialized view
CREATE MATERIALIZED VIEW IF NOT EXISTS public.agent_state_mv AS
SELECT
  id,
  agent_name,
  state,
  metadata,
  last_updated
FROM public.agent_states;

-- Index on materialized view
CREATE INDEX IF NOT EXISTS idx_agent_state_mv_agent_name ON public.agent_state_mv(agent_name);

-- Refresh function (security definer)
CREATE OR REPLACE FUNCTION public.refresh_agent_state_mv()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS 45872
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY public.agent_state_mv;
END;
45872;

-- Permissions for refresh function
REVOKE EXECUTE ON FUNCTION public.refresh_agent_state_mv() FROM PUBLIC;
Grant EXECUTE ON FUNCTION public.refresh_agent_state_mv() TO postgres;

-- Attempt to create pg_cron job
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    IF NOT EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'refresh_agent_state_mv_every_15s') THEN
      -- Note: pg_cron cron format doesn't support seconds; schedule every minute as fallback
      INSERT INTO cron.job(jobname, schedule, command)
      VALUES('refresh_agent_state_mv_every_15s', '*/1 * * * *', 'SELECT public.refresh_agent_state_mv();');
    END IF;
  ELSE
    RAISE NOTICE 'pg_cron extension not found; skipped cron job creation.';
  END IF;
END;
$$;
