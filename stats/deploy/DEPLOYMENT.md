# Stats Component Deployment

The Stats component enjoys a standalone deployment on a dedicated VPS (separate
from the UI and Scheduler).

- Github Actions
- Uses `appleboy/ssh-action@v1` to deploy over SSH
- Process runs as `systemd` service
- Uses `uv` to manage the Python environment and dependencies
