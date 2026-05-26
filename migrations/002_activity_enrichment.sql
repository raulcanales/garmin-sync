-- Per-activity enrichment (splits, HR zones, strength sets) and type-specific views.

CREATE TABLE IF NOT EXISTS garmin.activity_details (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES garmin.users(user_id) ON DELETE CASCADE,
  date DATE NOT NULL,
  source_id TEXT NOT NULL,
  activity_type TEXT,
  data JSONB NOT NULL,
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS activity_details_user_source_id_idx
  ON garmin.activity_details (user_id, source_id);

CREATE INDEX IF NOT EXISTS activity_details_user_type_date_idx
  ON garmin.activity_details (user_id, activity_type, date DESC);

-- Cross-type activity summary (Grafana + LLM overview).
DROP VIEW IF EXISTS garmin.v_activities;
CREATE VIEW garmin.v_activities AS
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
  (a.data->>'elevationGain')::numeric AS elevation_m,
  (a.data->>'calories')::numeric::int AS calories,
  (a.data->>'averageHR')::numeric::int AS avg_hr,
  (a.data->>'maxHR')::numeric::int AS max_hr,
  (a.data->>'aerobicTrainingEffect')::numeric AS aerobic_te,
  (a.data->>'anaerobicTrainingEffect')::numeric AS anaerobic_te,
  (a.data->>'activityTrainingLoad')::numeric AS training_load,
  (a.data->>'trainingStressScore')::numeric AS training_stress_score,
  (a.data->>'moderateIntensityMinutes')::numeric::int AS moderate_intensity_min,
  (a.data->>'vigorousIntensityMinutes')::numeric::int AS vigorous_intensity_min,
  (a.data->>'totalSets')::numeric::int AS total_sets,
  (a.data->>'totalReps')::numeric::int AS total_reps,
  a.synced_at
FROM garmin.activities a
JOIN garmin.users u ON u.user_id = a.user_id
WHERE a.source_id IS NOT NULL;

CREATE OR REPLACE VIEW garmin.v_running AS
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
  (a.data->>'elevationLoss')::numeric AS elevation_loss_m,
  (a.data->>'averageSpeed')::numeric AS avg_speed_mps,
  CASE
    WHEN COALESCE((a.data->>'averageSpeed')::numeric, 0) > 0
    THEN (1000.0 / (a.data->>'averageSpeed')::numeric) / 60.0
  END AS pace_min_per_km,
  (a.data->>'maxAverageSpeed')::numeric AS max_avg_speed_mps,
  (a.data->>'averageRunningCadenceInStepsPerMinute')::numeric AS avg_cadence,
  (a.data->>'maxRunningCadenceInStepsPerMinute')::numeric AS max_cadence,
  (a.data->>'avgStrideLength')::numeric AS avg_stride_length_m,
  (a.data->>'aerobicTrainingEffect')::numeric AS aerobic_te,
  (a.data->>'anaerobicTrainingEffect')::numeric AS anaerobic_te,
  (a.data->>'activityTrainingLoad')::numeric AS training_load,
  (a.data->>'trainingStressScore')::numeric AS training_stress_score,
  ad.data->'split_summaries' AS split_summaries,
  ad.data->'hr_zones' AS hr_zones,
  a.synced_at
FROM garmin.activities a
JOIN garmin.users u ON u.user_id = a.user_id
LEFT JOIN garmin.activity_details ad
  ON ad.user_id = a.user_id AND ad.source_id = a.source_id
WHERE a.source_id IS NOT NULL
  AND a.activity_type IN (
    'street_running',
    'trail_running',
    'treadmill_running',
    'virtual_run',
    'indoor_running',
    'track_running',
    'running'
  );

CREATE OR REPLACE VIEW garmin.v_strength AS
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
  (a.data->>'calories')::numeric::int AS calories,
  (a.data->>'averageHR')::numeric::int AS avg_hr,
  (a.data->>'maxHR')::numeric::int AS max_hr,
  (a.data->>'totalSets')::numeric::int AS total_sets,
  (a.data->>'totalReps')::numeric::int AS total_reps,
  (a.data->>'activeSets')::numeric::int AS active_sets,
  (a.data->>'aerobicTrainingEffect')::numeric AS aerobic_te,
  (a.data->>'anaerobicTrainingEffect')::numeric AS anaerobic_te,
  (a.data->>'activityTrainingLoad')::numeric AS training_load,
  (a.data->>'moderateIntensityMinutes')::numeric::int AS moderate_intensity_min,
  (a.data->>'vigorousIntensityMinutes')::numeric::int AS vigorous_intensity_min,
  (jsonb_array_length(COALESCE(ad.data->'exercise_sets', '[]'::jsonb)) > 0) AS has_set_detail,
  (
    SELECT string_agg(
      format(
        '%s %s×%s',
        COALESCE(s.elem->>'exercise_name', 'unknown'),
        COALESCE(s.elem->>'reps', '?'),
        CASE
          WHEN COALESCE((s.elem->>'weight_kg')::numeric, 0) > 0
          THEN trim(trailing '.' from to_char((s.elem->>'weight_kg')::numeric, 'FM999990.9')) || 'kg'
          ELSE 'BW'
        END
      ),
      '; ' ORDER BY (s.elem->>'set_order')::int NULLS LAST
    )
    FROM jsonb_array_elements(COALESCE(ad.data->'exercise_sets', '[]'::jsonb))
      WITH ORDINALITY AS s(elem, ord)
  ) AS exercises_summary,
  a.synced_at
FROM garmin.activities a
JOIN garmin.users u ON u.user_id = a.user_id
LEFT JOIN garmin.activity_details ad
  ON ad.user_id = a.user_id AND ad.source_id = a.source_id
WHERE a.source_id IS NOT NULL
  AND a.activity_type = 'strength_training';

CREATE OR REPLACE VIEW garmin.v_strength_sets AS
SELECT
  u.nickname,
  a.user_id,
  a.date,
  COALESCE(
    NULLIF(a.data->>'startTimeLocal', '')::timestamp,
    a.date::timestamp
  ) AS time,
  a.source_id AS activity_id,
  a.data->>'activityName' AS activity_name,
  (s.elem->>'set_order')::int AS set_order,
  s.elem->>'exercise_name' AS exercise_name,
  s.elem->>'category' AS category,
  (s.elem->>'reps')::int AS reps,
  (s.elem->>'weight_kg')::numeric AS weight_kg,
  (s.elem->>'duration_s')::numeric AS duration_s,
  s.elem->>'set_type' AS set_type
FROM garmin.activities a
JOIN garmin.users u ON u.user_id = a.user_id
JOIN garmin.activity_details ad
  ON ad.user_id = a.user_id AND ad.source_id = a.source_id
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(ad.data->'exercise_sets', '[]'::jsonb))
  WITH ORDINALITY AS s(elem, ord)
WHERE a.source_id IS NOT NULL
  AND a.activity_type = 'strength_training';
