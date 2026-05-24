CREATE TABLE IF NOT EXISTS garmin.users (
  user_id TEXT PRIMARY KEY,
  nickname TEXT NOT NULL,
  email TEXT NOT NULL,
  tokens JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS users_email_idx ON garmin.users (email);

-- Grafana user dropdown: registered accounts with nicknames.
CREATE OR REPLACE VIEW garmin.v_users AS
SELECT
  user_id,
  nickname,
  email,
  (tokens IS NOT NULL) AS logged_in,
  last_login_at
FROM garmin.users
ORDER BY nickname;
