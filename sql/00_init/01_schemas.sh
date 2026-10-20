#!/bin/bash
# Création des schémas médaillon et du rôle API en lecture seule.
# Exécuté par l'entrypoint Postgres uniquement à l'initialisation du volume.
set -euo pipefail

psql -v ON_ERROR_STOP=1 \
     -v api_user="$API_RO_USER" \
     -v api_pass="$API_RO_PASSWORD" \
     --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOSQL'
CREATE SCHEMA IF NOT EXISTS raw;      -- copie fidèle des sources
CREATE SCHEMA IF NOT EXISTS staging;  -- typé, nettoyé, dédupliqué
CREATE SCHEMA IF NOT EXISTS marts;    -- modèle analytique

CREATE ROLE :"api_user" LOGIN PASSWORD :'api_pass';
GRANT CONNECT ON DATABASE :"DBNAME" TO :"api_user";
GRANT USAGE ON SCHEMA marts TO :"api_user";
GRANT SELECT ON ALL TABLES IN SCHEMA marts TO :"api_user";
-- Tables créées plus tard (par dbt) lisibles automatiquement
ALTER DEFAULT PRIVILEGES IN SCHEMA marts GRANT SELECT ON TABLES TO :"api_user";
EOSQL
