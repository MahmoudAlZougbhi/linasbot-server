-- Apply on a new cluster with the migration job. Do not run this against production.
CREATE ROLE app_rw LOGIN;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw;

CREATE ROLE migrator LOGIN;
GRANT ALL ON SCHEMA public TO migrator;

CREATE ROLE readonly_analytics LOGIN;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_analytics;

CREATE ROLE qa_readonly LOGIN;
GRANT SELECT ON config_revisions, cm_published, platform_jobs, realtime_events TO qa_readonly;
