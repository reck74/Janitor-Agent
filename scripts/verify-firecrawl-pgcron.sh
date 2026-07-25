#!/usr/bin/env bash
# Verifica que el contenedor janitor-firecrawl-postgres tiene pg_cron instalado
# correctamente y que la base de datos coincide con el constraint de la imagen
# nuq-postgres (cron.database_name DEBE ser "postgres").
#
# Cambiado (BUG 8, firecrawl-deploy-fix.md):
#   - Lee de ~/.janitor/docker/firecrawl.env (no de ~/.janitor/.env)
#   - Usa POSTGRES_USER / POSTGRES_DB (no FIRECRAWL_POSTGRES_*)
#   - Verifica cron.database_name == "postgres" (no "firecrawl")
set -euo pipefail

ENV_FILE="${HOME}/.janitor/docker/firecrawl.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "FAIL: Environment file not found: $ENV_FILE"
    echo "      Ejecuta primero: bash ~/.janitor/skills/janitor-firecrawl/scripts/deploy.sh"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

if [[ -z "${POSTGRES_USER:-}" ]] || [[ -z "${POSTGRES_DB:-}" ]]; then
    echo "FAIL: POSTGRES_USER and POSTGRES_DB must be set in $ENV_FILE"
    exit 1
fi

if [[ "${POSTGRES_DB}" != "postgres" ]]; then
    echo "FAIL: POSTGRES_DB must be 'postgres' (nuq-postgres image constraint). Got: '${POSTGRES_DB}'"
    exit 1
fi

CONTAINER_NAME="janitor-firecrawl-postgres"
PSQL_CMD=(docker exec "$CONTAINER_NAME" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc)

echo -n "Check 1: pg_cron extension installed... "
RESULT=$("${PSQL_CMD[@]}" "SELECT 1 FROM pg_extension WHERE extname='pg_cron'" 2>/dev/null || true)
RESULT_TRIMMED=$(echo "$RESULT" | tr -d '[:space:]')
if [[ "$RESULT_TRIMMED" == "1" ]]; then
    echo "PASS"
else
    echo "FAIL"
    echo "  Expected: 1, Got: '$RESULT'"
    echo "  pg_cron extension is NOT installed in the $POSTGRES_DB database"
    exit 1
fi

echo -n "Check 2: cron.database_name set to postgres... "
RESULT=$("${PSQL_CMD[@]}" "SHOW cron.database_name" 2>/dev/null || true)
RESULT_TRIMMED=$(echo "$RESULT" | tr -d '[:space:]')
if [[ "$RESULT_TRIMMED" == "postgres" ]]; then
    echo "PASS"
else
    echo "FAIL"
    echo "  Expected: postgres, Got: '$RESULT'"
    echo "  cron.database_name is NOT set to postgres — nuq-postgres image is broken"
    exit 1
fi

echo -n "Check 3: Container health status... "
RESULT=$(docker inspect "$CONTAINER_NAME" --format='{{.State.Health.Status}}' 2>/dev/null || true)
RESULT_TRIMMED=$(echo "$RESULT" | tr -d '[:space:]')
if [[ "$RESULT_TRIMMED" == "healthy" ]]; then
    echo "PASS"
else
    echo "FAIL"
    echo "  Expected: healthy, Got: '$RESULT'"
    echo "  Container $CONTAINER_NAME is NOT healthy"
    exit 1
fi

echo ""
echo "All checks passed: pg_cron is properly installed in the postgres database"
exit 0
