#!/usr/bin/env bash
# Render start command for the MediFleet backend.
#
# Boot sequence:
#   1. Run seed_superadmin.py *if it still exists*. The seed is idempotent
#      (skips when the superadmin row is already there), so it is safe to
#      execute on every restart of the service.
#   2. Apply pending Alembic migrations to every active tenant database via
#      scripts/migrate_all_tenants.py. The script discovers tenants from the
#      master registry and is safe to re-run — it only applies pending work.
#      Legacy tenants (provisioned before Alembic was wired in) are
#      auto-bootstrapped on first contact.
#   3. Exec uvicorn so it inherits PID 1 and Render can deliver SIGTERM
#      cleanly on rollouts.
#
# Skipping migrations: set MIGRATE_ON_BOOT=0 to short-circuit step 2 (e.g.
# during incident response when you need the API up before chasing a
# migration regression).
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

if [[ "${MIGRATE_ON_BOOT:-1}" == "1" ]]; then
    echo ">> applying Alembic migrations to all tenant databases"
    if ! python scripts/migrate_all_tenants.py; then
        # A migration failure should block the deploy — a half-migrated
        # platform serves cryptic 500s like the one that prompted this
        # script. Exit non-zero so Render marks the deploy failed.
        echo "!! migrate_all_tenants.py failed — aborting deploy" >&2
        exit 1
    fi
else
    echo ">> MIGRATE_ON_BOOT=0 — skipping tenant migrations"
fi

PORT="${PORT:-8000}"
echo ">> launching uvicorn on 0.0.0.0:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
