#!/bin/bash
source "$(dirname "$0")/set_env.sh"
psql -d "$PGDATABASE"
