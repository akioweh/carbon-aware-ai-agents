#!/bin/bash
set -e
source "$(dirname "$0")/set_env.sh"

if ! pg_isready -q; then
    echo "Database is not running."
    exit 0
fi

echo "Stopping database server..."
pg_ctl -D "$PG_DATA" stop -m fast
echo "Database stopped."
