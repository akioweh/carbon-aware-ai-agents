#!/bin/bash
source "$(dirname "$0")/set_env.sh"

if pg_isready -h localhost -p "$PG_PORT" -q; then
    echo "Database is already running on port $PG_PORT."
    exit 0
fi

echo "Starting database server..."
pg_ctl -D "$PG_DATA" -o "-p $PG_PORT" -l "$PG_LOG" start
wait_for_db
echo "Database started. Logs are in $PG_LOG"
