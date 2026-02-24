#!/bin/bash
# Resolve absolute path for script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# If PG_HOME is set, add to PATH
if [ -n "$PG_HOME" ]; then
    export PATH="$PG_HOME/bin:$PATH"
fi

# Check if pg_ctl is available
if ! command -v pg_ctl &> /dev/null; then
    echo "Error: PostgreSQL tools (pg_ctl) not found in PATH."
    echo "Please add PostgreSQL bin directory to your PATH or set PG_HOME environment variable."
    exit 1
fi

export PG_DATA="$SCRIPT_DIR/../db_data"
export PG_PORT=5432
export PG_LOG="$SCRIPT_DIR/db.log"

# Standard Postgres environment variables
export PGHOST=localhost
export PGUSER=postgres
export PGDATABASE=calendar_db

# Security check for PG_DATA
if [[ "$PG_DATA" == "/" ]] || [[ "$PG_DATA" == "/home" ]] || [[ "$PG_DATA" == "/root" ]]; then
    echo "Error: PG_DATA is set to a dangerous path: $PG_DATA"
    exit 1
fi

wait_for_db() {
    echo "Waiting for database on port $PG_PORT..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if pg_isready -q; then
            echo "Database is ready."
            return 0
        fi
        sleep 1
        ((retries--))
    done
    echo "Timed out waiting for database."
    return 1
}
