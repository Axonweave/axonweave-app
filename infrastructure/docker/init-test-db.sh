#!/bin/bash
set -e
# Creates the test database used by pytest. Runs at postgres container first-init only.
psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE axonweave_test OWNER $POSTGRES_USER'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'axonweave_test')\gexec

    GRANT CONNECT ON DATABASE axonweave_test TO axonweave_app;
EOSQL
psql -U "$POSTGRES_USER" -d axonweave_test <<-EOSQL
    GRANT USAGE ON SCHEMA public TO axonweave_app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO axonweave_app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO axonweave_app;
EOSQL
