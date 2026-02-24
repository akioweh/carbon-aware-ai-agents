#!/bin/bash
APP_NAME="scheduler"

# 1. Find and kill by name
PID=$(pgrep -x "$APP_NAME")

if [ -z "$PID" ]; then
    echo "No process found for '$APP_NAME'."
else
    echo "Killing $APP_NAME (PID: $PID)..."
    kill -9 $PID
    
    # 2. Wait a moment for the kernel to release the socket
    sleep 0.2
    
    # 3. Final Verification
    if pgrep -x "$APP_NAME" > /dev/null; then
        echo "Error: Process $PID is stuck in 'D' state (uninterruptible)."
    else
        echo "Success: $APP_NAME terminated."
    fi
fi
