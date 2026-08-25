# PgBouncer for MediFleet

MediFleet is multi-tenant with **one Postgres database per tenant** (plus
`hms_master`) and runs multiple web workers/replicas. Without a pooler the app
can open `workers × cached-tenant-engines × DB_POOL_SIZE` upstream connections
(easily hundreds), so production should front Postgres with **PgBouncer in
`transaction` pool mode**. Full rationale + numbers: [`docs/DEPLOYMENT.md` §1](../../docs/DEPLOYMENT.md).

## Files

| File | Purpose |
|------|---------|
| `pgbouncer.ini` | Pooler config — wildcard `[databases]` (every tenant DB proxied), `pool_mode = transaction`. |
| `userlist.txt` | **Dev-only** plain-auth user list (compose Postgres defaults). Replace with SCRAM verifiers for prod. |

## Two moving parts

1. **Run PgBouncer** in front of Postgres (wildcard databases, transaction mode).
2. **Tell the app** to point at it and stop pooling itself:
   ```env
   DATABASE_URL=postgresql://<user>:<pass>@<pgbouncer-host>:6432/hms_master
   DB_POOLER_ENABLED=true
   ```
   `DB_POOLER_ENABLED=true` switches every SQLAlchemy engine to `NullPool`, so
   the pooler owns pooling and the app never double-pools. Leave it `false` when
   connecting straight to Postgres.

## Local rehearsal (docker compose)

```bash
# brings up postgres, redis, backend, frontend AND pgbouncer
docker compose --profile pgbouncer up --build
```
To route the backend through it, set in `.env` before `up`:
```env
DATABASE_URL=postgresql://medifleet:medifleet@pgbouncer:6432/hms_master
DB_POOLER_ENABLED=true
```
(without the profile / these vars, the stack talks to Postgres directly as before).

## Production hardening

- **Auth:** set `auth_type = scram-sha-256` in `pgbouncer.ini` and generate a
  hashed `userlist.txt` (the SCRAM verifier is already stored in
  `pg_authid.rolpassword`):
  ```bash
  psql "$ADMIN_DATABASE_URL" -Atq \
    -c "SELECT '\"'||rolname||'\" \"'||rolpassword||'\"' FROM pg_authid WHERE rolname='hms';" \
    > userlist.txt
  ```
- **Sizing:** `default_pool_size × active-tenant-DBs` must stay under Postgres
  `max_connections`; cap with `max_db_connections`. Raise `THREADPOOL_TOKENS`
  (app) only in step with the pool budget.
- **Transaction-mode caveats:** no cross-transaction session state — no
  session-scoped advisory locks, `LISTEN/NOTIFY`, or session `SET`. The app
  already complies (the OP-number lock is `pg_advisory_xact_lock`, released at
  COMMIT).
- **Managed Postgres (e.g. Render):** if you can't run a PgBouncer sidecar, use
  the provider's managed transaction-mode pooler endpoint as `DATABASE_URL` and
  still set `DB_POOLER_ENABLED=true`.
