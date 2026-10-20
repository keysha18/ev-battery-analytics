#!/bin/bash
# Smoke test du socle : schémas présents, rôle API en lecture seule sur marts uniquement.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

admin() { docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tA "$@"; }
api()   { docker compose exec -T -e PGPASSWORD="$API_RO_PASSWORD" postgres \
            psql -h localhost -U "$API_RO_USER" -d "$POSTGRES_DB" -tA "$@"; }

fail=0
check() {  # check <description> <attendu> <obtenu>
  if [ "$2" = "$3" ]; then echo "OK   $1"; else echo "FAIL $1 (attendu '$2', obtenu '$3')"; fail=1; fi
}

check "schémas raw/staging/marts" "marts raw staging" \
  "$(admin -c "select string_agg(schema_name, ' ' order by schema_name) from information_schema.schemata where schema_name in ('raw','staging','marts')")"
check "api_ro peut lire marts" "t" "$(api -c "select has_schema_privilege('marts','USAGE')")"
check "api_ro ne voit pas raw" "f" "$(api -c "select has_schema_privilege('raw','USAGE')")"
check "api_ro ne voit pas staging" "f" "$(api -c "select has_schema_privilege('staging','USAGE')")"
check "api_ro n'est pas superuser" "f" "$(api -c "select rolsuper from pg_roles where rolname = current_user")"
check "api_ro ne peut pas créer dans marts" "f" "$(api -c "select has_schema_privilege('marts','CREATE')")"

# Après `make dbt-build` : l'API (rôle api_ro) doit lire les marts et rien d'autre
if [ "$(admin -c "select to_regclass('marts.dim_battery') is not null")" = "t" ]; then
  check "api_ro lit marts.dim_battery (34 cellules)" "34" "$(api -c "select count(*) from marts.dim_battery")"
  check "api_ro refusé sur staging.stg_nasa_cycles" "denied" \
    "$(api -c "select 1 from staging.stg_nasa_cycles limit 1" >/dev/null 2>&1 && echo readable || echo denied)"
  check "api_ro refusé sur raw.nasa_cycles" "denied" \
    "$(api -c "select 1 from raw.nasa_cycles limit 1" >/dev/null 2>&1 && echo readable || echo denied)"
fi

exit $fail
