#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HOME}/.janitor/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "FAIL: Environment file not found: $ENV_FILE"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

if [[ -z "${FIRECRAWL_POSTGRES_USER:-}" ]] || [[ -z "${FIRECRAWL_POSTGRES_DB:-}" ]]; then
    echo "FAIL: FIRECRAWL_POSTGRES_USER and FIRECRAWL_POSTGRES_DB must be set in $ENV_FILE"
    exit 1
fi

CONTAINER_NAME="janitor-firecrawl-postgres"
PSQL_CMD=(docker exec "$CONTAINER_NAME" psql -U "$FIRECRAWL_POSTGRES_USER" -d "$FIRECRAWL_POSTGRES_DB" -tAc)

echo -n "Check 1: pg_cron extension installed... "
RESULT=$("${PSQL_CMD[@]}" "SELECT 1 FROM pg_extension WHERE extname='pg_cron'" 2>/dev/null || true)
RESULT_TRIMMED=$(echo "$RESULT" | tr -d '[:space:]')
if [[ "$RESULT_TRIMMED" == "1" ]]; then
    echo "PASS"
else
    echo "FAIL"
    echo "  Expected: 1, Got: '$RESULT'"
    echo "  pg_cron extension is NOT installed in the firecrawl database"
    exit 1
fi

echo -n "Check 2: cron.database_name set to firecrawl... "
RESULT=$("${PSQL_CMD[@]}" "SHOW cron.database_name" 2>/dev/null || true)
RESULT_TRIMMED=$(echo "$RESULT" | tr -d '[:space:]')
if [[ "$RESULT_TRIMMED" == "firecrawl" ]]; then
    echo "PASS"
else
    echo "FAIL"
    echo "  Expected: firecrawl, Got: '$RESULT'"
    echo "  cron.database_name is NOT set to firecrawl"
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
echo "All checks passed: pg_cron is properly installed in firecrawl database"
exit 0
