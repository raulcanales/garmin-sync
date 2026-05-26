-- items_fetched now stores per-table max(synced_at) ISO timestamps, not row counts.
COMMENT ON COLUMN garmin.sync_log.items_fetched IS
  'Per-table latest synced_at for the user at job finish (derived from data tables)';
