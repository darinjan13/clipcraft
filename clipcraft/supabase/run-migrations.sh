#!/bin/bash
# Apply all Supabase migrations in order.
#
# Prerequisites:
#   - supabase CLI installed (npm install -g supabase)
#   - supabase linked to project: supabase link --project-ref <ref>
#   - or run directly via: psql $DATABASE_URL -f <file>
#
# Usage:
#   ./run-migrations.sh                          # via supabase CLI
#   DATABASE_URL=postgresql://... ./run-migrations.sh   # via psql
#
# Migrations are idempotent (IF NOT EXISTS / OR REPLACE).

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)/migrations"
MIGRATIONS=(
  "001_create_all_tables.sql"
  "002_add_job_claiming.sql"
  "003_asset_path_functions.sql"
  "004_core_backend_foundation.sql"
  "005_video_job_events.sql"
  "006_add_soft_delete.sql"
  "007_ai_provider_credentials.sql"
  "008_provider_connection_test_statuses.sql"
  "009_video_job_configuration_snapshots.sql"
  "010_ai_application_preferences.sql"
  "20260822120000_narration_export_style.sql"
)

echo "=== ClipCraft AI — Migration Runner ==="
echo ""

if [ -n "${DATABASE_URL:-}" ]; then
  echo "Mode: direct psql (DATABASE_URL set)"
  for m in "${MIGRATIONS[@]}"; do
    echo "  Applying: $m ..."
    psql "$DATABASE_URL" -f "$DIR/$m" -1 -q
    echo "  ✓ $m applied"
  done
elif command -v supabase &>/dev/null; then
  echo "Mode: supabase CLI"
  for m in "${MIGRATIONS[@]}"; do
    echo "  Applying: $m ..."
    supabase db execute --file "$DIR/$m"
    echo "  ✓ $m applied"
  done
else
  echo "ERROR: Neither DATABASE_URL nor supabase CLI available."
  echo ""
  echo "Options:"
  echo "  1. Export DATABASE_URL and re-run:"
  echo "     export DATABASE_URL=postgresql://<user>:<pass>@<host>:5432/postgres"
  echo "     ./run-migrations.sh"
  echo ""
  echo "  2. Install supabase CLI and link project:"
  echo "     npm install -g supabase"
  echo "     supabase link --project-ref <ref>"
  echo "     supabase db remote set"
  echo "     ./run-migrations.sh"
  echo ""
  echo "  3. Apply manually:"
  for m in "${MIGRATIONS[@]}"; do
    echo "     psql \$DATABASE_URL -f \"$DIR/$m\" -1 -q"
  done
  exit 1
fi

echo ""
echo "=== All migrations applied ==="

# Run verification
echo ""
echo "=== Running verification ==="
if [ -n "${DATABASE_URL:-}" ]; then
  psql "$DATABASE_URL" -f "$DIR/verify-migrations.sql" -q
else
  supabase db execute --file "$DIR/verify-migrations.sql"
fi
echo "  Verification complete"
