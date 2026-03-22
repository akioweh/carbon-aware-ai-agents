#!/bin/bash
set -e

echo "Starting application startup script..."

if [ -n "$PGHOST" ]; then
  echo "Database host specified: $PGHOST"
  echo "Running database initialization..."
  psql -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" -d "$PGDATABASE" -f init.sql || {
    echo "Warning: Initializing database failed..."
  }
else
  echo "No PGHOST provided. Skipping database initialization."
fi

echo "Starting scheduler..."
exec ./scheduler
