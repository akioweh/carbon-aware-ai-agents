#!/bin/bash
source "$(dirname "$0")/set_env.sh"
psql -h localhost -p $PG_PORT -U postgres -d calendar_db
