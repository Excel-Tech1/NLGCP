#!/usr/bin/env bash
set -uo pipefail

healthy=0
failed=1

report_http() {
  local label=$1 url=$2
  if curl --silent --fail --max-time 3 "$url" >/dev/null; then
    printf '%-18s HEALTHY\n' "$label"
  else
    printf '%-18s FAILED\n' "$label"
    healthy=1
  fi
}

if docker compose ps --status running postgres 2>/dev/null | grep -q postgres; then
  if docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null && test "$(psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT postgis_version()")" != ""'; then
    printf '%-18s HEALTHY\n' "PostgreSQL/PostGIS"
  else
    printf '%-18s FAILED\n' "PostgreSQL/PostGIS"
    healthy=1
  fi
else
  printf '%-18s NOT INSTALLED\n' "PostgreSQL/PostGIS"
fi

report_http "NATS/JetStream" "http://localhost:${NATS_MONITOR_PORT:-8222}/healthz?js-enabled-only=true"

if command -v redis-cli >/dev/null 2>&1; then
  if redis-cli -u "${REDIS_URL:-redis://localhost:6379/0}" ping 2>/dev/null | grep -q PONG; then
    printf '%-18s HEALTHY\n' "Redis"
  else
    printf '%-18s FAILED\n' "Redis"
    healthy=1
  fi
elif docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
  printf '%-18s HEALTHY\n' "Redis"
else
  printf '%-18s NOT INSTALLED\n' "Redis"
fi

report_http "API" "http://localhost:${API_PORT:-8000}/health"
report_http "Frontend" "http://localhost:${WEB_PORT:-3000}/"

if command -v rnx2rtkp >/dev/null 2>&1; then
  printf '%-18s HEALTHY\n' "RTKLIB"
else
  printf '%-18s NOT INSTALLED\n' "RTKLIB"
fi

if command -v pride_pppar >/dev/null 2>&1 || command -v pdp3 >/dev/null 2>&1; then
  printf '%-18s HEALTHY\n' "PRIDE PPP-AR"
else
  printf '%-18s NOT INSTALLED\n' "PRIDE PPP-AR"
fi

exit "$healthy"
