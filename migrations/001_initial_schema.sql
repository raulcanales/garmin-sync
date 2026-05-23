CREATE SCHEMA IF NOT EXISTS garmin;

CREATE TABLE IF NOT EXISTS garmin.activities (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  activity_type TEXT,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS activities_user_source_id_idx
  ON garmin.activities (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS activities_user_date_idx
  ON garmin.activities (user_id, date)
  WHERE source_id IS NULL;

CREATE INDEX IF NOT EXISTS activities_user_activity_type_date_idx
  ON garmin.activities (user_id, activity_type, date DESC);

CREATE TABLE IF NOT EXISTS garmin.sleep (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS sleep_user_source_id_idx
  ON garmin.sleep (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS sleep_user_date_idx
  ON garmin.sleep (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.daily_summary (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS daily_summary_user_source_id_idx
  ON garmin.daily_summary (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS daily_summary_user_date_idx
  ON garmin.daily_summary (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.body_battery (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS body_battery_user_source_id_idx
  ON garmin.body_battery (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS body_battery_user_date_idx
  ON garmin.body_battery (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.hrv (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS hrv_user_source_id_idx
  ON garmin.hrv (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS hrv_user_date_idx
  ON garmin.hrv (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.heart_rate (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS heart_rate_user_source_id_idx
  ON garmin.heart_rate (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS heart_rate_user_date_idx
  ON garmin.heart_rate (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.stress (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS stress_user_source_id_idx
  ON garmin.stress (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS stress_user_date_idx
  ON garmin.stress (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.body_composition (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS body_composition_user_source_id_idx
  ON garmin.body_composition (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS body_composition_user_date_idx
  ON garmin.body_composition (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.floors (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS floors_user_source_id_idx
  ON garmin.floors (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS floors_user_date_idx
  ON garmin.floors (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.training_readiness (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS training_readiness_user_source_id_idx
  ON garmin.training_readiness (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS training_readiness_user_date_idx
  ON garmin.training_readiness (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.morning_training_readiness (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS morning_training_readiness_user_source_id_idx
  ON garmin.morning_training_readiness (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS morning_training_readiness_user_date_idx
  ON garmin.morning_training_readiness (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.training_status (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS training_status_user_source_id_idx
  ON garmin.training_status (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS training_status_user_date_idx
  ON garmin.training_status (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.max_metrics (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  source_id TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS max_metrics_user_source_id_idx
  ON garmin.max_metrics (user_id, source_id)
  WHERE source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS max_metrics_user_date_idx
  ON garmin.max_metrics (user_id, date)
  WHERE source_id IS NULL;

CREATE TABLE IF NOT EXISTS garmin.sync_log (
  id BIGSERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  error TEXT,
  items_fetched JSONB
);
