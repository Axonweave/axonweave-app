-- Creates restricted application role and test database.
-- The owner/migration role is created via POSTGRES_USER in docker-compose.

-- Create application role if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'axonweave_app') THEN
        CREATE ROLE axonweave_app WITH LOGIN PASSWORD 'axonweave_app_dev_password';
    END IF;
END
$$;

-- Grant connect and usage on main DB
GRANT CONNECT ON DATABASE axonweave TO axonweave_app;
GRANT USAGE ON SCHEMA public TO axonweave_app;

-- Grant DML (no DDL) on all current and future tables
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO axonweave_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO axonweave_app;

-- Grant usage on sequences (needed for serial/UUID generation)
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO axonweave_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO axonweave_app;
