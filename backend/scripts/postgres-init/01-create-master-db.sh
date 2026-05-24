#!/usr/bin/env bash
# Bootstraps the multi-tenant Postgres cluster on first container start.
#
# On a brand-new postgres volume, this script runs once (postgres only
# executes /docker-entrypoint-initdb.d/* when the data directory is empty).
# It creates:
#   - hms_master (the platform-level registry DB)
# Tenant DBs are created on-demand by tenant_provisioning.py during onboarding,
# so there's nothing to seed for them here.
#
# Note: POSTGRES_DB is created automatically by the postgres entrypoint, so
# `hms_master` is already there if the env var matches. This script is a
# safety net for the case where someone overrides POSTGRES_DB.

set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE hms_master'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'hms_master')\gexec
EOSQL

echo "Postgres init complete — hms_master is ready."
