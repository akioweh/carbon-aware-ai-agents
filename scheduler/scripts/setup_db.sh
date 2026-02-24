#!/bin/bash
set -e
source "$(dirname "$0")/set_env.sh"

# 1. Initialize DB cluster
if [ ! -d "$PG_DATA" ] || [ -z "$(ls -A "$PG_DATA")" ]; then
    echo "Initializing database cluster at $PG_DATA..."
    mkdir -p "$PG_DATA"
    initdb -D "$PG_DATA" -U "$PGUSER" -A trust -E UTF8
else
    echo "Database cluster already exists at $PG_DATA."
fi

# 2. Start database server
if pg_isready -q; then
    echo "Database is already running."
else
    echo "Starting database server..."
    pg_ctl -D "$PG_DATA" -o "-p $PG_PORT -k /tmp" -l "$PG_LOG" start
    wait_for_db
fi

# 3. Setup database
echo "Setting up database '$PGDATABASE'..."

# Create database if it doesn't exist
if ! psql -lqt -d postgres | cut -d \| -f 1 | grep -qw "$PGDATABASE"; then
    createdb -U "$PGUSER" "$PGDATABASE"
else
    echo "Database '$PGDATABASE' already exists."
fi

# Initialize tables
psql -d "$PGDATABASE" -f "$SCRIPT_DIR/../sql/init.sql"

echo "Setup complete. Database is running on port $PG_PORT."
echo "You can stop it using ./stop_db.sh"
