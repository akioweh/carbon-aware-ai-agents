#!/bin/bash
set -e
source "$(dirname "$0")/set_env.sh"

if pg_isready -q; then
    echo "Database is already running on port $PG_PORT."
    exit 0
fi

echo "Starting database server..."
pg_ctl -D "$PG_DATA" -o "-p $PG_PORT -k /tmp" -l "$PG_LOG" start
wait_for_db
echo "Database started. Logs: $PG_LOG"
