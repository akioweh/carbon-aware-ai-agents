#!/bin/bash
source "$(dirname "$0")/set_env.sh"

if [ ! -f "$PG_DATA/PG_VERSION" ]; then
    echo "Initializing database cluster at $PG_DATA..."
    rm -rf "$PG_DATA"/*
    mkdir -p "$PG_DATA"
    initdb -D "$PG_DATA" -U postgres -A trust -E UTF8
else
    echo "Database cluster already exists at $PG_DATA."
fi

if pg_isready -h localhost -p "$PG_PORT" -q; then
    echo "Database is already running."
else
    echo "Starting database server..."
    pg_ctl -D "$PG_DATA" -o "-p $PG_PORT -k /tmp" -l "$PG_LOG" start
    wait_for_db
fi

echo "Setting up user and database..."
psql -h localhost -p $PG_PORT -U postgres -d postgres -c "ALTER USER postgres WITH PASSWORD '123';"

# Check if db exists
if ! psql -h localhost -p $PG_PORT -U postgres -lqt | cut -d \| -f 1 | grep -qw calendar_db; then
    createdb -h localhost -p $PG_PORT -U postgres calendar_db
else
    echo "Database calendar_db already exists."
fi

psql -h localhost -p $PG_PORT -U postgres -d calendar_db -f "$SCRIPT_DIR/../sql/init.sql"

echo "Setup complete. Database is running on port $PG_PORT."
echo "You can stop it using ./stop_db.sh"
