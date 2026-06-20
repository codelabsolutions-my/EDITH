-- Rollback for 0001_init.sql.
-- depends:

DROP TABLE IF EXISTS usage_log;
DROP TABLE IF EXISTS action_log;
DROP TRIGGER IF EXISTS memories_search_vector_trg ON memories;
DROP FUNCTION IF EXISTS memories_search_vector_update();
DROP TABLE IF EXISTS memories;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS conversations;
DROP TABLE IF EXISTS refresh_tokens;
DROP TABLE IF EXISTS provider_accounts;
DROP TABLE IF EXISTS users;
