-- Coach / LLM state: goals, athlete notes, planned workouts.

CREATE TABLE IF NOT EXISTS garmin.goals (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT,
  target_date DATE,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'completed', 'abandoned')),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS goals_user_status_idx
  ON garmin.goals (user_id, status);

CREATE TABLE IF NOT EXISTS garmin.athlete_notes (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id) ON DELETE CASCADE,
  category TEXT NOT NULL DEFAULT 'general'
    CHECK (category IN ('injury', 'preference', 'schedule', 'pr', 'equipment', 'general')),
  content TEXT NOT NULL,
  supersedes_id INTEGER REFERENCES garmin.athlete_notes(id) ON DELETE SET NULL,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS athlete_notes_user_active_idx
  ON garmin.athlete_notes (user_id, active)
  WHERE active = true;

CREATE TABLE IF NOT EXISTS garmin.planned_workouts (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id) ON DELETE CASCADE,
  planned_date DATE NOT NULL,
  status TEXT NOT NULL DEFAULT 'planned'
    CHECK (status IN ('planned', 'completed', 'skipped', 'modified')),
  workout_type TEXT,
  prescription TEXT NOT NULL,
  linked_activity_id TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS planned_workouts_user_date_idx
  ON garmin.planned_workouts (user_id, planned_date DESC);
