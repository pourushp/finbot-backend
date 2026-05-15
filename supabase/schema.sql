-- FinBot Database Schema for Supabase
-- Run this in the Supabase SQL Editor (https://supabase.com/dashboard)

-- Watchlists
CREATE TABLE IF NOT EXISTS watchlists (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  symbol TEXT NOT NULL,
  added_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, symbol)
);

-- Portfolio Holdings
CREATE TABLE IF NOT EXISTS portfolio_holdings (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  symbol TEXT NOT NULL,
  quantity DECIMAL NOT NULL DEFAULT 0,
  buy_price DECIMAL NOT NULL DEFAULT 0,
  buy_date DATE,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Price Alerts
CREATE TABLE IF NOT EXISTS price_alerts (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  symbol TEXT NOT NULL,
  target_price DECIMAL NOT NULL,
  direction TEXT CHECK (direction IN ('above', 'below')) NOT NULL,
  active BOOLEAN DEFAULT TRUE,
  triggered_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User Preferences
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
  default_currency TEXT DEFAULT 'INR',
  email_alerts BOOLEAN DEFAULT TRUE,
  push_alerts BOOLEAN DEFAULT TRUE,
  theme TEXT DEFAULT 'dark',
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Row Level Security (RLS)
ALTER TABLE watchlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_holdings ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

-- Policies: users can only see/modify their own data
CREATE POLICY "Users manage own watchlists" ON watchlists FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users manage own holdings" ON portfolio_holdings FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users manage own alerts" ON price_alerts FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Users manage own preferences" ON user_preferences FOR ALL USING (auth.uid() = user_id);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_holdings_user ON portfolio_holdings(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_active ON price_alerts(active, symbol) WHERE active = TRUE;
