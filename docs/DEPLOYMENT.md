# Production Deployment — Scaling Notes

This file documents the infrastructure expectations for running the MediFleet
backend in production at scale (multi-tenant, multi-worker, multi-replica).

## 1. PostgreSQL connection pooling (PgBouncer)

The MediFleet backend uses one SQLAlchemy engine per tenant, cached behind a
bounded LRU (`TENANT_ENGINE_CACHE_SIZE`, default 32). With 200 tenants and
4 uvicorn workers, that's still up to `4 × 32 × DB_POOL_SIZE` = 640 pooled
connections from the application alone — too many for a vanilla Postgres
instance to handle without a dedicated pooler.

**Recommendation: front Postgres with PgBouncer in `transaction` pool mode.**

### Sample PgBouncer configuration

```ini
[databases]
* = host=postgres-primary.internal port=5432

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt

pool_mode = transaction
max_client_conn = 2000
default_pool_size = 25
reserve_pool_size = 5
reserve_pool_timeout = 5
server_idle_timeout = 600
```

### Application-side settings

In `.env`, point `DATABASE_URL` at PgBouncer (port 6432) and tune the per-engine
pool to be small — PgBouncer is doing the real pooling:

```env
DATABASE_URL=postgresql://hms:secret@pgbouncer.internal:6432/mayoclinic_db
DB_POOL_SIZE=2
DB_MAX_OVERFLOW=4
DB_POOL_RECYCLE_SECONDS=1800
TENANT_ENGINE_CACHE_SIZE=32
```

> ⚠️ With PgBouncer in `transaction` mode, do NOT use server-side prepared
> statements that span transactions, advisory locks, or session-level
> features. Our codebase already avoids these.

## 2. WebSocket pub/sub (Redis)

The default `ConnectionManager` keeps connections in an in-process dict.
That works for single-worker dev, but with multiple workers a notification
sent from worker-A never reaches a client whose socket lives on worker-B.

When `REDIS_URL` is set, the manager publishes every notification to a Redis
channel (`hms:user:{id}` or `hms:role:{name}`) and a listener task in each
worker forwards it to its locally-attached sockets. This makes broadcasts
correct across any number of workers and replicas.

```env
REDIS_URL=redis://redis.internal:6379/0
```

For HA, use Redis Sentinel or a managed Redis (ElastiCache, Memorystore, Upstash).

## 3. Tenant provisioning

`POST /api/public/hospitals` is the production-grade provisioning endpoint.
It creates the database, applies the schema, seeds RBAC, and returns a
one-time admin password. The endpoint is intentionally synchronous — for
self-service signup at scale, wrap it in a background job and email the
temp password rather than returning it inline.

## 4. CORS

`CORS_ORIGINS` must be set to a closed list of trusted origins in production:

```env
CORS_ORIGINS=https://hospital-a.example.com,https://hospital-b.example.com
```

## 5. Secrets

`SECRET_KEY` (JWT signing) and `ENCRYPTION_KEY` (column-level encryption)
must be independent random 32+ byte values. Compromising one must not
compromise the other.

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 6. Worker model

`backend/render-start.sh` now launches **gunicorn managing uvicorn workers**
directly — no manual command needed. The worker count is driven by the
`WEB_CONCURRENCY` env var (default `1`, so the out-of-the-box deploy is a single
worker). To scale a worker up:

```bash
# Set on the host / Render dashboard:
WEB_CONCURRENCY=4          # ~2 × vCPU
REDIS_URL=redis://…        # REQUIRED for >1 worker (cross-worker WS fan-out)
GUNICORN_TIMEOUT=120       # optional override (default 120s)
GUNICORN_MAX_REQUESTS=2000 # optional; recycles workers to cap memory
```

The script refuses nothing but prints a loud warning if `WEB_CONCURRENCY > 1`
while `REDIS_URL` is unset — without Redis, a notification or payment event
published on one worker never reaches a socket living on another.

`--max-requests` (+ jitter) periodically recycles each worker, capping the
long-lived memory footprint of the per-worker tenant-engine LRU cache.

### Per-worker concurrency (thread pool)

~245 of the API handlers are synchronous `def`, which FastAPI runs in AnyIO's
thread pool (default 40 threads = the ceiling on concurrent in-flight DB-bound
requests per worker). `THREADPOOL_TOKENS` (default 40) lifts that ceiling — but
each busy thread can hold one DB connection, so only raise it in step with the
database's connection budget (i.e. behind PgBouncer).

### Response speed

The API returns `ORJSONResponse` by default (3–5× faster JSON encoding than the
stdlib) and GZip-compresses responses above `GZIP_MIN_SIZE` bytes (default 500),
which is the dominant latency term for large payloads (charts, statements,
queues) on slower hospital links.

## 7. Append-only audit triggers

Migration `d4f2e8b03c11` installs PostgreSQL triggers that block UPDATE and
DELETE on `audit_logs` and `data_access_logs`. Run `alembic upgrade head`
on every tenant database.
