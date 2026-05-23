-- Fix v_activities: Garmin stores some activity fields as "259.0" which ::int rejects.

CREATE OR REPLACE VIEW garmin.v_activities AS
SELECT
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
WHERE a.source_id IS NOT NULL;
