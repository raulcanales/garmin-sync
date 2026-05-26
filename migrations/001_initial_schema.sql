CREATE SCHEMA IF NOT EXISTS garmin;

CREATE TABLE IF NOT EXISTS garmin.users (
  user_id SERIAL PRIMARY KEY,
  nickname TEXT NOT NULL,
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  telegram_id BIGINT,
  date_of_birth DATE NOT NULL,
  gender TEXT NOT NULL CHECK (gender IN ('male', 'female')),
  tokens JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS users_nickname_idx ON garmin.users (nickname);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_idx ON garmin.users (email);
CREATE UNIQUE INDEX IF NOT EXISTS users_telegram_id_idx ON garmin.users (telegram_id) WHERE telegram_id IS NOT NULL;



CREATE TABLE IF NOT EXISTS garmin.activities (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
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
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id),
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  error TEXT,
  items_fetched JSONB
);

CREATE OR REPLACE VIEW garmin.v_users AS
SELECT
  user_id,
  nickname,
  name,
  email,
  telegram_id,
  date_of_birth,
  gender,
  (tokens IS NOT NULL) AS logged_in,
  last_login_at
FROM garmin.users
ORDER BY nickname;

CREATE OR REPLACE VIEW garmin.v_daily_metrics AS
WITH days AS (
  SELECT user_id, date FROM garmin.daily_summary
  UNION
  SELECT user_id, date FROM garmin.sleep
  UNION
  SELECT user_id, date FROM garmin.hrv
  UNION
  SELECT user_id, date FROM garmin.stress
  UNION
  SELECT user_id, date FROM garmin.body_battery
  UNION
  SELECT user_id, date FROM garmin.heart_rate
  UNION
  SELECT user_id, date FROM garmin.training_readiness
  UNION
  SELECT user_id, date FROM garmin.morning_training_readiness
  UNION
  SELECT user_id, date FROM garmin.training_status
  UNION
  SELECT user_id, date FROM garmin.floors
  UNION
  SELECT user_id, date FROM garmin.max_metrics
)
SELECT
  u.nickname,
  d.user_id,
  d.date,
  d.date::timestamp AS time,

  -- Daily summary
  (ds.data->>'totalSteps')::bigint AS steps,
  (ds.data->>'totalKilocalories')::numeric AS total_calories,
  (ds.data->>'activeKilocalories')::numeric AS active_calories,
  (ds.data->>'bmrKilocalories')::numeric AS bmr_calories,
  (ds.data->>'distanceInMeters')::numeric / 1000.0 AS distance_km,
  (ds.data->>'floorsAscended')::numeric AS floors_ascended,
  (ds.data->>'floorsDescended')::numeric AS floors_descended,
  COALESCE(
    (ds.data->>'restingHeartRate')::int,
    (hr.data->>'restingHeartRate')::int
  ) AS resting_hr,
  COALESCE(
    (ds.data->>'maxHeartRate')::int,
    (hr.data->>'maxHeartRate')::int
  ) AS max_hr,
  COALESCE(
    (ds.data->>'minHeartRate')::int,
    (hr.data->>'minHeartRate')::int
  ) AS min_hr,
  (ds.data->>'vigorousIntensityMinutes')::int AS vigorous_minutes,
  (ds.data->>'moderateIntensityMinutes')::int AS moderate_minutes,
  (ds.data->>'intensityMinutesGoal')::int AS intensity_minutes_goal,

  -- Sleep (Garmin may nest under dailySleepDTO)
  COALESCE(
    (s.data->'dailySleepDTO'->'sleepScores'->'overall'->>'value')::int,
    (s.data->'sleepScores'->'overall'->>'value')::int
  ) AS sleep_score,
  COALESCE(
    (s.data->'dailySleepDTO'->>'sleepTimeSeconds')::bigint,
    (s.data->>'sleepTimeSeconds')::bigint
  ) / 3600.0 AS sleep_hours,
  COALESCE(
    (s.data->'dailySleepDTO'->>'deepSleepSeconds')::bigint,
    (s.data->>'deepSleepSeconds')::bigint
  ) / 3600.0 AS deep_sleep_hours,
  COALESCE(
    (s.data->'dailySleepDTO'->>'lightSleepSeconds')::bigint,
    (s.data->>'lightSleepSeconds')::bigint
  ) / 3600.0 AS light_sleep_hours,
  COALESCE(
    (s.data->'dailySleepDTO'->>'remSleepSeconds')::bigint,
    (s.data->>'remSleepSeconds')::bigint
  ) / 3600.0 AS rem_sleep_hours,
  COALESCE(
    (s.data->'dailySleepDTO'->>'awakeSleepSeconds')::bigint,
    (s.data->>'awakeSleepSeconds')::bigint
  ) / 3600.0 AS awake_hours,
  COALESCE(
    (s.data->'dailySleepDTO'->>'restlessMomentsCount')::int,
    (s.data->'dailySleepDTO'->>'restlessMoments')::int,
    (s.data->>'restlessMoments')::int
  ) AS restless_moments,
  COALESCE(
    (s.data->'dailySleepDTO'->>'avgSleepHeartRate')::int,
    (s.data->>'avgSleepHeartRate')::int
  ) AS avg_sleep_hr,
  COALESCE(
    (s.data->'dailySleepDTO'->>'avgSleepHRV')::numeric,
    (s.data->>'avgSleepHRV')::numeric
  ) AS avg_sleep_hrv,
  COALESCE(
    (s.data->'dailySleepDTO'->>'avgSleepRespiration')::numeric,
    (s.data->>'avgSleepRespiration')::numeric
  ) AS avg_sleep_respiration,

  -- HRV
  (h.data->'hrvSummary'->>'lastNightAvg')::numeric AS hrv_last_night,
  (h.data->'hrvSummary'->>'weeklyAvg')::numeric AS hrv_weekly_avg,
  (h.data->'hrvSummary'->>'lastNight5MinHigh')::numeric AS hrv_last_night_high,
  (h.data->'hrvSummary'->>'lastNight5MinLow')::numeric AS hrv_last_night_low,
  COALESCE(
    h.data->'hrvSummary'->>'status',
    h.data->'hrvSummary'->>'hrvStatus'
  ) AS hrv_status,
  COALESCE(
    (h.data->'hrvSummary'->>'baselineBalancedLow')::numeric,
    (h.data->'hrvSummary'->'baseline'->>'balancedLow')::numeric
  ) AS hrv_baseline_low,
  COALESCE(
    (h.data->'hrvSummary'->>'baselineBalancedHigh')::numeric,
    (h.data->'hrvSummary'->'baseline'->>'balancedUpper')::numeric,
    (h.data->'hrvSummary'->'baseline'->>'balancedHigh')::numeric
  ) AS hrv_baseline_high,

  -- Stress
  (st.data->>'avgStressLevel')::int AS stress_avg,
  (st.data->>'maxStressLevel')::int AS stress_max,
  (st.data->>'restStressDuration')::bigint / 60.0 AS rest_stress_minutes,
  (st.data->>'lowStressDuration')::bigint / 60.0 AS low_stress_minutes,
  (st.data->>'mediumStressDuration')::bigint / 60.0 AS medium_stress_minutes,
  (st.data->>'highStressDuration')::bigint / 60.0 AS high_stress_minutes,

  -- Body battery (intraday array stored per day)
  bb_stats.high AS body_battery_high,
  bb_stats.low AS body_battery_low,
  bb_stats.charged AS body_battery_charged,
  bb_stats.drained AS body_battery_drained,

  -- Training readiness
  COALESCE(
    CASE WHEN jsonb_typeof(tr.data) = 'array' THEN tr.data->0->>'score' END,
    tr.data->>'score',
    CASE WHEN jsonb_typeof(tr.data) = 'array' THEN tr.data->0->>'trainingReadinessScore' END,
    tr.data->>'trainingReadinessScore'
  )::int AS training_readiness,
  COALESCE(
    CASE WHEN jsonb_typeof(mtr.data) = 'array' THEN mtr.data->0->>'score' END,
    mtr.data->>'score',
    CASE WHEN jsonb_typeof(mtr.data) = 'array' THEN mtr.data->0->>'trainingReadinessScore' END,
    mtr.data->>'trainingReadinessScore'
  )::int AS morning_training_readiness,

  -- Training status
  COALESCE(
    ts.data->>'trainingStatus',
    ts.data->0->>'trainingStatus'
  ) AS training_status,
  COALESCE(
    (ts.data->>'weeklyTrainingLoad')::numeric,
    (ts.data->0->>'weeklyTrainingLoad')::numeric
  ) AS weekly_training_load,
  COALESCE(
    (ts.data->>'loadFocus')::numeric,
    (ts.data->0->>'loadFocus')::numeric
  ) AS load_focus,

  -- Floors (dedicated table; daily summary also has floorsAscended)
  COALESCE(
    (fl.data->>'floorsAscended')::numeric,
    (fl.data->>'value')::numeric
  ) AS floors_climbed,

  -- Max metrics (VO2 max etc.)
  COALESCE(
    (mm.data->0->>'vo2MaxValue')::numeric,
    (mm.data->>'vo2MaxValue')::numeric,
    (mm.data->0->>'vo2MaxPreciseValue')::numeric,
    (mm.data->>'vo2MaxPreciseValue')::numeric
  ) AS vo2_max

FROM days d
JOIN garmin.users u ON u.user_id = d.user_id
LEFT JOIN garmin.daily_summary ds
  ON ds.user_id = d.user_id AND ds.date = d.date
LEFT JOIN garmin.sleep s
  ON s.user_id = d.user_id AND s.date = d.date
LEFT JOIN garmin.hrv h
  ON h.user_id = d.user_id AND h.date = d.date
LEFT JOIN garmin.stress st
  ON st.user_id = d.user_id AND st.date = d.date
LEFT JOIN garmin.heart_rate hr
  ON hr.user_id = d.user_id AND hr.date = d.date
LEFT JOIN garmin.training_readiness tr
  ON tr.user_id = d.user_id AND tr.date = d.date
LEFT JOIN garmin.morning_training_readiness mtr
  ON mtr.user_id = d.user_id AND mtr.date = d.date
LEFT JOIN garmin.training_status ts
  ON ts.user_id = d.user_id AND ts.date = d.date
LEFT JOIN garmin.floors fl
  ON fl.user_id = d.user_id AND fl.date = d.date
LEFT JOIN garmin.max_metrics mm
  ON mm.user_id = d.user_id AND mm.date = d.date
LEFT JOIN garmin.body_battery bb
  ON bb.user_id = d.user_id AND bb.date = d.date
LEFT JOIN LATERAL (
  SELECT
    MAX(
      COALESCE(
        (elem->>'bodyBatteryLevel')::int,
        (elem->>'value')::int
      )
    ) AS high,
    MIN(
      COALESCE(
        (elem->>'bodyBatteryLevel')::int,
        (elem->>'value')::int
      )
    ) AS low,
    MAX((elem->>'charged')::numeric) AS charged,
    MAX((elem->>'drained')::numeric) AS drained
  FROM jsonb_array_elements(
    CASE
      WHEN bb.data IS NULL THEN '[]'::jsonb
      WHEN jsonb_typeof(bb.data) = 'array' THEN bb.data
      WHEN bb.data ? 'bodyBatteryValuesArray' THEN bb.data->'bodyBatteryValuesArray'
      ELSE '[]'::jsonb
    END
  ) elem
) bb_stats ON true;

CREATE OR REPLACE VIEW garmin.v_activities AS
SELECT
  u.nickname,
  a.user_id,
  a.date,
  COALESCE(
    NULLIF(a.data->>'startTimeLocal', '')::timestamp,
    a.date::timestamp
  ) AS time,
  a.activity_type,
  a.source_id AS activity_id,
  a.data->>'activityName' AS name,
  (a.data->>'duration')::numeric / 60.0 AS duration_min,
  (a.data->>'distance')::numeric / 1000.0 AS distance_km,
  (a.data->>'calories')::numeric::int AS calories,
  (a.data->>'averageHR')::numeric::int AS avg_hr,
  (a.data->>'maxHR')::numeric::int AS max_hr,
  (a.data->>'elevationGain')::numeric AS elevation_m,
  (a.data->>'averageSpeed')::numeric AS avg_speed_mps,
  (a.data->>'averageRunningCadenceInStepsPerMinute')::numeric AS avg_cadence,
  a.synced_at
FROM garmin.activities a
JOIN garmin.users u ON u.user_id = a.user_id
WHERE a.source_id IS NOT NULL;

CREATE OR REPLACE VIEW garmin.v_body_composition AS
SELECT
  u.nickname,
  bc.user_id,
  bc.date,
  bc.date::timestamp AS time,
  COALESCE(
    (bc.data->>'weight')::numeric / 1000.0,
    (bc.data->>'weightInGrams')::numeric / 1000.0
  ) AS weight_kg,
  (bc.data->>'bodyFat')::numeric AS body_fat_pct,
  (bc.data->>'bodyWater')::numeric AS body_water_pct,
  (bc.data->>'muscleMass')::numeric AS muscle_mass_g,
  (bc.data->>'boneMass')::numeric AS bone_mass_g,
  bc.synced_at
FROM garmin.body_composition bc
JOIN garmin.users u ON u.user_id = bc.user_id;

CREATE OR REPLACE VIEW garmin.v_sync_log AS
SELECT
  u.nickname,
  sl.user_id,
  sl.started_at,
  sl.finished_at,
  sl.status,
  sl.error,
  sl.items_fetched,
  EXTRACT(EPOCH FROM (sl.finished_at - sl.started_at)) AS duration_seconds
FROM garmin.sync_log sl
JOIN garmin.users u ON u.user_id = sl.user_id;
