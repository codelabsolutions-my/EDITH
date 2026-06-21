-- Rollback for 0002_proactivity.sql.
-- depends: 0001_init

DROP TABLE IF EXISTS reminders;
DROP TABLE IF EXISTS device_tokens;
