#!/usr/bin/env bash
# Render start command for the HMS backend.
#
# Boot sequence:
#   1. Run seed_superadmin.py *if it still exists*. The seed is idempotent
#      (skips when the superadmin row is already there), so it is safe to
#      execute on every restart of the service.
#   2. Once the operator deletes seed_superadmin.py and redeploys, this
#      script silently skips step 1 and goes straight to step 2.
#   3. Exec uvicorn so it inherits PID 1 and Render can deliver SIGTERM
#      cleanly on rollouts.
#
# Configure on Render (Web Service):
#   Build Command : pip install -r requirements.txt
#   Start Command : ./render-start.sh
set -euo pipefail

cd "$(dirname "$0")"

if [[ -f "seed_superadmin.py" ]]; then
    echo ">> seed_superadmin.py present — running platform bootstrap"
    # Don't take the API down if the seed itself fails (e.g. transient DB
    # outage) — log loudly and continue. Render's logs will surface this.
    if ! python seed_superadmin.py; then
        echo "!! seed_superadmin.py exited non-zero — continuing to uvicorn anyway" >&2
    fi
else
    echo ">> seed_superadmin.py not present — skipping bootstrap"
fi

PORT="${PORT:-8000}"
echo ">> launching uvicorn on 0.0.0.0:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
