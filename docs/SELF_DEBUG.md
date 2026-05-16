# MediFleet Self-Debugging Guide

**System**: MediFleet Hospital Management System  
**Audience**: IT/DevOps Staff and Hospital Administrators  
**Last Updated**: 2026-05-16

---

## How to Use This Guide

**Who this guide is for:**
- IT administrators managing MediFleet infrastructure
- DevOps engineers handling deployments and integrations
- Hospital administrators troubleshooting day-to-day issues
- On-call engineers responding to production incidents

**Severity levels used in this guide:**

| Level | Description | Example |
|-------|-------------|---------|
| **Critical** | System is down or patient data may be compromised | Backend unreachable, cross-tenant data leak |
| **High** | Core functionality broken for multiple users | Auth failures, migration errors, M-Pesa down |
| **Medium** | Feature degraded for some users | Module gating cache stale, WebSocket single-worker |
| **Low** | Cosmetic or non-blocking issue | Slow dashboard, frontend build warning |

**When to escalate to MediFleet Support:**
- Any cross-tenant data isolation failure (Critical — do not attempt self-remediation beyond containment)
- Alembic revision conflicts you cannot resolve with `stamp head`
- KDPA breach incidents requiring legal/compliance guidance
- Persistent `UniqueConstraint` failures after applying documented SQL fixes
- Any incident involving suspected token theft or MITM attack
- Production database corruption

Contact: support@medifleet.io — include your `db_name` (tenant identifier), timestamp of first occurrence, and the exact error string from logs.

---

## Part 1: Quick Diagnostic Checklist

Run these six checks in order before diving into specific sections. They cover the most common root causes.

### Check 1: Backend Health

```bash
curl -s https://<your-backend-url>/api/ | python3 -m json.tool
```

Expected response:
```json
{"status": "Operational"}
```

If you get a connection refused, 502, or 504 — go to Part 2.1 (Startup Failures) or Part 5.2 (Render.com deployment issues).

### Check 2: Database Reachable

```bash
psql "$DATABASE_URL" -c "SELECT version();"
```

Or with explicit parameters:
```bash
psql -h <host> -U <user> -d hms_master -c "\l"
```

Expected: A list of databases including `hms_master` and all tenant databases. If this fails, the backend cannot start. Go to Part 2.3.

### Check 3: Redis Running

```bash
redis-cli -u "$REDIS_URL" ping
```

Expected response: `PONG`

If Redis is down, the system will still run but:
- WebSocket notifications will only work within a single uvicorn worker
- Dashboard cache is disabled (slower load times)
- Go to Part 2.6 and Part 2.7 for impact details.

### Check 4: Tenant DB Migrated

```bash
psql "$DATABASE_URL" -c "SELECT datname FROM pg_database WHERE datname LIKE 'hospital_%';"
```

Then for each tenant database, verify a core table exists:
```bash
psql -h <host> -U <user> -d <tenant_db_name> -c "\dt patients"
```

If you see `relation "patients" does not exist`, the migration did not complete for that tenant. Go to Part 2.3.

### Check 5: M-Pesa Config Active

Connect to the relevant tenant database and run:
```sql
SELECT id, shortcode, is_active, environment FROM mpesa_configs LIMIT 5;
```

If `is_active` is `FALSE` or no row exists, M-Pesa payments will fail with `"M-Pesa is not configured or is inactive."` Go to Part 2.5.

### Check 6: Module Enabled

Connect to `hms_master` and check the tenant's feature flags:
```sql
SELECT db_name, feature_flags FROM tenants WHERE db_name = 'your_hospital_db_name';
```

Expected for an active module:
```json
{"radiology": true, "pharmacy": true, "lab": true}
```

If a module key is `false` or missing, users will receive HTTP 402. Go to Part 2.4.

---

## Part 2: Backend Errors (FastAPI / Python)

### 2.1 Startup Failures

#### Error: `"DATABASE_URL is empty — set it on the host environment"`

**Severity**: Critical  
**Cause**: The `DATABASE_URL` environment variable is not set. The backend refuses to start.

**Diagnostic steps:**
1. Check that the variable is set in your environment:
   ```bash
   echo $DATABASE_URL
   ```
2. On Docker Compose, verify your `.env` file or `docker-compose.yml` `environment:` block.
3. On Render.com, go to your Web Service → Environment → confirm `DATABASE_URL` is present.

**Fix:**
Set `DATABASE_URL` to a valid PostgreSQL connection string. On Render.com, this is typically auto-injected when you link a Postgres database. If you are copying the value manually, ensure it starts with `postgresql://` (see next error).

---

#### Error: `"DATABASE_URL must start with postgresql://"`

**Severity**: Critical  
**Cause**: Render.com provides connection strings beginning with `postgres://` (without `ql`). Python's SQLAlchemy requires `postgresql://`.

**Fix:**
The application contains normalization logic in the startup config. If the error still appears, manually override in your environment:
```bash
# Replace postgres:// with postgresql://
export DATABASE_URL="postgresql://user:pass@host:5432/hms_master"
```

In Render.com shell or environment override:
```
DATABASE_URL=postgresql://user:pass@host:5432/hms_master
```

Do not rely on copy-pasting the Internal Database URL from Render without verifying the prefix.

---

#### Missing `SECRET_KEY`

**Severity**: Critical  
**Cause**: JWT signing key not set. The application will either fail startup or produce unsigned tokens (depending on version).

**Fix:**
Generate a cryptographically strong key:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Set it as `SECRET_KEY` in your environment. Never reuse keys across environments (sandbox vs. production).

---

#### Missing `ENCRYPTION_KEY`

**Severity**: High  
**Cause**: AES encryption key for M-Pesa credentials not set. M-Pesa configuration cannot be stored or retrieved.

**Fix:**
Generate a 32-byte (256-bit) key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set as `ENCRYPTION_KEY`. If you rotate this key, all stored M-Pesa credentials must be re-entered in the admin panel.

---

### 2.2 Authentication Errors

#### Error: `"X-Tenant-ID header is required. Pick a hospital before signing in."`

**Severity**: Medium  
**Cause**: The frontend did not send the `X-Tenant-ID` header. This header identifies which hospital database to use for authentication.

**Diagnostic steps:**
1. Open browser DevTools → Network tab → find the failing request.
2. Confirm `X-Tenant-ID` is present in Request Headers.
3. Confirm the value matches a `db_name` in the `tenants` table in `hms_master`.

**Fix:**
- If the hospital picker is not showing: check that the tenant has `is_active = TRUE` in `hms_master.tenants`.
- If the header is being sent but rejected: confirm the `db_name` value exactly matches (case-sensitive).

```sql
-- In hms_master
SELECT id, name, db_name, is_active FROM tenants WHERE is_active = TRUE;
```

---

#### Error: `"Account locked. Try again in N minutes."`

**Severity**: Medium  
**Cause**: The user account is locked after 5 consecutive failed login attempts. The lockout duration is 15 minutes.

**Diagnostic steps:**
```sql
-- In the relevant tenant database
SELECT email, failed_login_attempts, locked_until FROM users WHERE email = 'user@example.com';
```

**Fix (manual unlock):**
```sql
-- In the relevant tenant database
UPDATE users
SET failed_login_attempts = 0, locked_until = NULL
WHERE email = 'user@example.com';
```

Note: Wait for the 15-minute window to expire if this is a legitimate user who simply forgot their password. Manual unlock should only be performed after confirming identity.

---

#### Error: `"CSRF verification failed. Missing or invalid token."`

**Severity**: Medium  
**Cause**: The double-submit CSRF protection failed. The request is either:
- Missing the `csrf_token` cookie
- Missing the `x-csrf-token` request header
- The cookie and header values do not match

**Diagnostic steps:**
1. Open DevTools → Application → Cookies. Look for `csrf_token`.
2. Open DevTools → Network → failing request → Request Headers. Look for `x-csrf-token`.
3. Confirm the values match.

**Common causes:**
- Session expired and cookies cleared but the frontend retained a stale CSRF token in memory.
- Browser privacy extensions blocking cookie writes.
- Cross-origin request without proper CORS setup (see `CORS_ORIGINS` environment variable).

**Fix:**
- Instruct the user to clear browser cookies and log in again.
- Verify `CORS_ORIGINS` in your backend environment includes the exact frontend origin (e.g., `https://hospital.medifleet.io`).
- Verify nginx (or reverse proxy) is forwarding cookies and custom headers to the backend.

---

#### Error: `"Refresh token reuse detected — all sessions revoked"`

**Severity**: High (security event)  
**Cause**: A refresh token was submitted twice. The token rotation scheme detected that a previously-used (already rotated) token was submitted again. This indicates either a replay attack or a compromised token. The system immediately revokes ALL refresh tokens for the affected user.

**Immediate actions:**
1. The user must log in again — all sessions are terminated.
2. Review Part 8.3 for full incident response.

---

#### Error: `"Cross-tenant refresh forbidden"`

**Severity**: High  
**Cause**: A refresh token issued for Tenant A was submitted with a `X-Tenant-ID` header for Tenant B. This is rejected with HTTP 403.

**Fix:**
- This is almost always a frontend bug where the tenant context changed after login without clearing the stored refresh token.
- Instruct the user to clear cookies and log in again.
- If this occurs repeatedly for a user without them changing hospitals, escalate — it may indicate token leakage.

---

#### Error: `"Invalid or already-used reset token"`

**Severity**: Low  
**Cause**: Password reset tokens are single-use and time-limited. Either:
- The token was already used.
- The token expired.
- The user requested multiple resets and is using an old link.

**Fix:** User must request a new password reset. Rate limit is 3 requests per minute per IP.

---

### 2.3 Database Errors

#### Error: `relation "X" does not exist`

**Severity**: High  
**Cause**: Alembic migrations have not been applied to the tenant database, or a new migration was added but not run.

**Diagnostic steps:**
1. Check which revision the tenant database is at:
   ```bash
   cd /home/user/HMS-2/backend
   alembic -x db_url="postgresql://user:pass@host:5432/tenant_db_name" current
   ```
2. Compare to the latest revision:
   ```bash
   alembic heads
   ```

**Fix — run migrations for all tenants:**
```bash
cd /home/user/HMS-2/backend
python scripts/migrate_all_tenants.py
```

**Fix — run migration for a single tenant:**
```bash
cd /home/user/HMS-2/backend
alembic -x db_url="postgresql://user:pass@host:5432/tenant_db_name" upgrade head
```

---

#### Error: SSL EOF / Connection Refused to PostgreSQL

**Severity**: Critical  
**Cause**: The PostgreSQL server is unreachable. Common causes:
- PostgreSQL container/service not running
- Wrong host or port in `DATABASE_URL`
- Firewall or security group blocking port 5432
- SSL required but not configured (Render.com requires `sslmode=require`)

**Diagnostic steps:**
```bash
# Test TCP connectivity
nc -zv <postgres_host> 5432

# Test with psql including SSL
psql "postgresql://user:pass@host:5432/hms_master?sslmode=require" -c "SELECT 1;"
```

**Fix:**
- Confirm PostgreSQL is running: `docker ps | grep postgres` or check Render.com dashboard.
- Add `?sslmode=require` to your `DATABASE_URL` if connecting to Render.com Postgres.
- Check security groups/firewall rules allow inbound 5432 from your backend's IP range.

---

#### UniqueConstraint on `license_number` (empty string not converted to NULL)

**Severity**: Medium  
**Cause**: When a doctor's license number is left blank in the UI, some versions of the form submit an empty string `""` instead of `NULL`. PostgreSQL treats empty strings as distinct values for most comparisons, but `UNIQUE` constraints treat each `""` as a duplicate of another `""`.

**Diagnostic steps:**
```sql
-- In the tenant database
SELECT id, email, license_number FROM doctors WHERE license_number = '';
```

**Fix:**
```sql
-- Convert empty strings to NULL
UPDATE doctors SET license_number = NULL WHERE license_number = '';
```

Ensure the frontend sends `null` (not `""`) for optional fields. If the issue recurs, contact MediFleet Support to apply a database-level check constraint.

---

#### Alembic: `"Target database is not up to date"`

**Severity**: High  
**Cause**: The database schema is behind the codebase's latest migration. Usually occurs after a backend deployment.

**Fix:**
```bash
cd /home/user/HMS-2/backend
alembic upgrade head

# Or for all tenant databases:
python scripts/migrate_all_tenants.py
```

---

#### Alembic: `"Can't locate revision"`

**Severity**: High  
**Cause**: The `alembic_version` table in the database references a revision ID that no longer exists in the migrations folder. This can happen after:
- A migration file was deleted
- A branch merge conflict left an orphaned revision
- The database was restored from a backup with a newer schema

**Diagnostic steps:**
```bash
cd /home/user/HMS-2/backend
alembic history --verbose
alembic current
```

Compare the current revision in the database against the `alembic history` output.

**Fix — stamp head (use only after manually verifying the schema is correct):**
```bash
cd /home/user/HMS-2/backend
# First verify the actual schema matches what head expects
alembic check

# If schema is correct but version table is wrong:
alembic stamp head
```

**Warning:** `stamp head` does not run any SQL — it only updates the `alembic_version` table. Only use this if you have confirmed (by inspecting `\d` in psql) that the actual table structure matches the latest migration's expectations. If in doubt, escalate to MediFleet Support.

---

### 2.4 Module Gating Errors

#### HTTP 402 "Module Unavailable"

**Severity**: Medium  
**Cause**: The requested feature (e.g., Radiology, Lab) is not enabled in the hospital's `feature_flags`. The system returns HTTP 402 for any endpoint guarded by a disabled module.

**Diagnostic steps:**
```sql
-- In hms_master
SELECT db_name, feature_flags FROM tenants WHERE db_name = 'your_hospital_db_name';
```

**Fix — enable a module:**
```sql
-- In hms_master
UPDATE tenants
SET feature_flags = jsonb_set(feature_flags::jsonb, '{radiology}', 'true')
WHERE db_name = 'hospital_db_name';
```

Replace `radiology` with the module key (e.g., `lab`, `pharmacy`, `billing`).

**Important — cache TTL:**
The `feature_flags` value is cached for 60 seconds. After updating the database, users will see the change within 60 seconds without any restart needed. Do not restart the backend to clear the cache for this purpose alone.

**Always-on modules:** Some core modules (e.g., `patients`, `appointments`) cannot be disabled regardless of `feature_flags`. Attempting to set them to `false` has no effect.

---

### 2.5 M-Pesa Errors

#### Error: `"M-Pesa is not configured or is inactive."`

**Severity**: High  
**Cause**: No active `MpesaConfig` row exists for this tenant, or `is_active = FALSE`.

**Diagnostic steps:**
```sql
-- In the tenant database
SELECT id, shortcode, is_active, environment FROM mpesa_configs;
```

**Fix:**
- If no row: Add M-Pesa configuration via the Hospital Admin panel (Finance → M-Pesa Settings).
- If `is_active = FALSE`: Enable via admin panel or:
  ```sql
  UPDATE mpesa_configs SET is_active = TRUE WHERE id = <config_id>;
  ```

---

#### Error: `"Failed to authenticate with Safaricom Daraja API"`

**Severity**: High  
**Cause**: The consumer key/secret stored in the database (AES-encrypted) are invalid or expired, or the `MPESA_ENV` does not match the credentials (sandbox credentials used against production endpoint).

**Diagnostic steps — test Daraja credentials directly:**

For sandbox:
```bash
curl -X GET \
  "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials" \
  -H "Authorization: Basic $(echo -n 'your_consumer_key:your_consumer_secret' | base64)"
```

For production:
```bash
curl -X GET \
  "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials" \
  -H "Authorization: Basic $(echo -n 'your_consumer_key:your_consumer_secret' | base64)"
```

Expected response:
```json
{"access_token": "...", "expires_in": "3599"}
```

If you get a 400 or 401, the credentials themselves are wrong. Re-enter them via the admin panel.

**Fix:**
1. Log in to the Safaricom Developer Portal (developer.safaricom.co.ke).
2. Retrieve the correct Consumer Key and Consumer Secret for your app.
3. Re-enter them in MediFleet Admin → Finance → M-Pesa Settings.
4. Confirm `MPESA_ENV` is set to `sandbox` or `production` to match.

---

#### Error: `"The balance is insufficient"` (Safaricom result_desc)

**Severity**: Low (user-facing)  
**Cause**: The customer's M-Pesa wallet does not have sufficient funds.

**Fix:** Inform the patient. No system action required. The STK push transaction will show `status = FAILED` in the payments table.

---

#### Error: `"Request cancelled by user"` (Safaricom result_desc)

**Severity**: Low (user-facing)  
**Cause**: The customer dismissed the M-Pesa STK push prompt on their phone.

**Fix:** Offer to resend the payment request. No system action required.

---

#### Sandbox: Ngrok Callback URL Not Resolving

**Severity**: Medium (sandbox only)  
**Cause**: M-Pesa sandbox callbacks require a public URL. In local/sandbox mode, the system auto-detects Ngrok via `http://127.0.0.1:4040/api/tunnels`. If Ngrok is not running, callbacks will fail and payments will remain in `PENDING` state indefinitely.

**Setup Ngrok for sandbox:**
```bash
# Install ngrok if not present
# https://ngrok.com/download

# Start ngrok tunnel to backend port
ngrok http 8000
```

The system will log: `"Auto-resolved Ngrok Callback URL: https://xxxx.ngrok.io"` on the next STK push.

**Verify Ngrok is detected:**
```bash
curl -s http://127.0.0.1:4040/api/tunnels | python3 -m json.tool
```

Look for a `public_url` starting with `https://`.

---

#### Production: Callback URL Not Whitelisted

**Severity**: High (production)  
**Cause**: Safaricom Daraja API will not send callbacks to URLs not registered in the portal.

**Fix:**
1. Log in to developer.safaricom.co.ke.
2. Navigate to your application → Go Live → Callback URL.
3. Enter your production backend URL: `https://your-backend.onrender.com/api/payments/mpesa/callback/`.
4. Save and wait up to 15 minutes for propagation.

---

### 2.6 WebSocket Errors

#### Error: `"REDIS_URL not configured. WebSocket broadcasts will not span workers."`

**Severity**: Medium  
**Cause**: Redis is not configured. When uvicorn/gunicorn runs multiple workers (typical in production), WebSocket events published by Worker A are not visible to clients connected to Worker B.

**Impact:**
- Real-time notifications (e.g., new appointment, lab result ready) may not reach all connected users.
- Single-worker deployments are not affected.

**Fix:**
Set `REDIS_URL` in your environment:
```
REDIS_URL=redis://localhost:6379/0
# Or for Redis with auth:
REDIS_URL=redis://:your_password@your_redis_host:6379/0
```

Restart the backend after setting this variable.

---

#### WebSocket Connection Refused / 101 Not Returned

**Severity**: Medium  
**Cause**: Nginx or a reverse proxy is not forwarding the WebSocket upgrade handshake.

**Fix — required nginx configuration:**
```nginx
location /ws/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400;
}
```

The `Upgrade` and `Connection` headers are mandatory for WebSocket proxying. Without them, nginx returns a standard HTTP response instead of upgrading the connection.

---

### 2.7 Performance Issues

#### Slow Patient Search (ILIKE vs. Trigram Index)

**Symptom**: Patient search by name is slow (>500ms) on large datasets.  
**Cause**: `ILIKE '%name%'` queries cannot use standard B-tree indexes. A leading wildcard forces a full sequential scan.

**Fix — enable pg_trgm and create index:**
```sql
-- In the tenant database
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_patients_name_trgm
  ON patients USING gin (full_name gin_trgm_ops);
```

After creating the index, `ILIKE '%name%'` queries will use the trigram index automatically.

---

#### Slow Dashboard Load (Redis Down)

**Symptom**: Dashboard takes 3–8 seconds to load.  
**Cause**: The dashboard aggregates data (bed occupancy, revenue, appointment counts) using queries cached in Redis with a 30-second TTL. If Redis is unavailable, every dashboard load hits the database directly.

**Fix:** Restore Redis (see Check 3 above). Dashboard cache will repopulate automatically within 30 seconds of Redis coming back online.

---

#### High Memory Usage (TENANT_ENGINE_CACHE_SIZE)

**Symptom**: Backend process memory grows continuously and does not stabilize.  
**Cause**: The backend maintains an LRU cache of SQLAlchemy engines — one per tenant database. The default cache size is 32. If you have more than 32 active tenants and they all receive traffic, the cache evicts and recreates engines frequently, each holding connection pool memory.

**Fix:**
Increase the cache size via environment variable:
```
TENANT_ENGINE_CACHE_SIZE=64
```

Or reduce connection pool size per engine if memory is the constraint:
```
DB_POOL_SIZE=1
DB_MAX_OVERFLOW=2
```

Default values: `DB_POOL_SIZE=2`, `DB_MAX_OVERFLOW=4`.

---

#### Connection Pool Exhaustion

**Symptom**: Requests fail with `QueuePool limit of size X overflow Y reached` or similar SQLAlchemy pool error.  
**Cause**: Too many concurrent requests are holding database connections. With the default pool (2 + 4 = 6 connections per tenant engine), high concurrency tenants can exhaust their pool.

**Diagnostic steps:**
```sql
-- Check active connections per tenant database (run in hms_master)
SELECT datname, count(*) as connections
FROM pg_stat_activity
GROUP BY datname
ORDER BY connections DESC;

-- Or for a specific tenant:
SELECT count(*) FROM pg_stat_activity WHERE datname = 'hospital_db';
```

**Fix options:**
1. Increase `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` (requires restart):
   ```
   DB_POOL_SIZE=5
   DB_MAX_OVERFLOW=10
   ```
2. Deploy PgBouncer in transaction pooling mode in front of PostgreSQL to multiplex many application connections into fewer server connections.
3. Check for long-running transactions holding connections:
   ```sql
   SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
   FROM pg_stat_activity
   WHERE state != 'idle' AND query_start < now() - interval '30 seconds'
   ORDER BY duration DESC;
   ```

---

## Part 3: Frontend Errors (React / Vite)

### 3.1 Build and Start Errors

#### Vite Build Fails: `VITE_API_URL is not defined`

**Cause**: The `VITE_API_URL` environment variable was not set at build time. Vite bakes environment variables into the bundle at build time, not runtime.

**Fix:**
Set the variable before building:
```bash
VITE_API_URL=https://your-backend.onrender.com npm run build
```

On Vercel, set `VITE_API_URL` in Project Settings → Environment Variables. Trigger a new deployment after adding the variable.

---

#### TypeScript / ESLint Build Errors

**Fix:**
```bash
cd /home/user/HMS-2/frontend
npm install
npm run build 2>&1 | head -50
```

Read the first error carefully — subsequent errors are often cascading from the first. Fix the root cause.

---

### 3.2 API Call Failures

#### HTTP 403 with `"CSRF verification failed. Missing or invalid token."`

**Cause**: See Part 2.2. On the frontend side, the `axios` instance (or `fetch` wrapper) must:
1. Send cookies with every request (`withCredentials: true` in axios).
2. Read the `csrf_token` cookie value and send it as the `x-csrf-token` header on all non-GET requests.

**Diagnostic steps:**
1. Open DevTools → Application → Cookies → confirm `csrf_token` exists.
2. Open DevTools → Network → failing POST/PUT/DELETE request → Request Headers → look for `x-csrf-token`.

---

#### HTTP 401 After Inactivity

**Cause**: Access tokens (JWT HttpOnly cookies) expire. The frontend should automatically use the refresh token endpoint to obtain a new access token. If the refresh also fails, the user must log in again.

**Expected behavior:** User is redirected to the login page. If they are not being redirected, check the axios response interceptor for 401 handling.

---

#### HTTP 400 with `"X-Tenant-ID header is required"`

**Cause**: The frontend did not attach the `X-Tenant-ID` header. This is stored in the application's tenant context (typically in React context or localStorage after hospital selection).

**Diagnostic steps:**
1. Open DevTools → Network → failing request → Request Headers.
2. If `X-Tenant-ID` is missing, the tenant context was lost (page refresh, logout, or bug in context persistence).

**Fix:** Instruct the user to return to the hospital picker and re-select their hospital. If this happens on every page load, check that the tenant selection is persisted (e.g., in `localStorage` or `sessionStorage`) and re-read on app initialization.

---

### 3.3 Module Guard Appearing Unexpectedly (60-Second Cache)

**Symptom**: A module was just enabled in the database but users still see "Module Unavailable."  
**Cause**: `feature_flags` are cached server-side for 60 seconds. The cache has not expired yet.

**Fix:** Wait up to 60 seconds. No restart or cache flush is needed. If the issue persists beyond 60 seconds, verify the SQL update was committed:
```sql
SELECT feature_flags FROM tenants WHERE db_name = 'hospital_db_name';
```

---

### 3.4 WebSocket / Real-Time Failures

#### Symptom: No Real-Time Notifications in Production

**Diagnostic steps:**
1. Open DevTools → Network → filter by "WS" (WebSocket).
2. Confirm a WebSocket connection is established (status 101).
3. If status is 200 or 404, the WebSocket upgrade is not being proxied correctly — see Part 2.6 nginx configuration.
4. If the connection establishes but no messages arrive, Redis may be down — see Check 3.

**Symptom: WebSocket works for one user but not another on the same page**  
**Cause**: Multi-worker deployment without Redis. The two users are connected to different uvicorn workers that cannot share events.  
**Fix:** Configure `REDIS_URL`. See Part 2.6.

---

## Part 4: Multi-Tenant Isolation Issues

### 4.1 Patient Data from Another Hospital Appearing

**Severity**: Critical — treat as a security breach until proven otherwise.

**Immediate containment steps:**
1. Document the exact time of discovery, the user who reported it, and what data was visible.
2. Do NOT attempt to explain or rationalize — assume breach until investigation proves otherwise.
3. Immediately deactivate the user account whose session may have been involved:
   ```sql
   -- In the tenant database
   UPDATE users SET is_active = FALSE WHERE email = 'affected_user@example.com';
   ```
4. Revoke all sessions for that user:
   ```sql
   UPDATE refresh_tokens SET revoked = TRUE
   WHERE user_id = (SELECT user_id FROM users WHERE email = 'affected_user@example.com');
   ```
5. Check backend logs for the time window — look for any `X-Tenant-ID` header anomalies or errors logged as `AUTH_ERROR`.
6. Review audit logs from both tenant databases in the relevant time window:
   ```sql
   SELECT * FROM audit_logs
   WHERE timestamp BETWEEN '2026-05-16 10:00:00' AND '2026-05-16 11:00:00'
   ORDER BY timestamp;
   ```
7. Escalate immediately to MediFleet Support and your hospital's Data Protection Officer.
8. Begin KDPA breach response — see Part 8.2.

---

### 4.2 Staff Seeing Another Tenant's Data

**Severity**: Critical  
**Cause**: This should be architecturally impossible (each tenant has its own database). If reported, possible causes include:
- A bug in the tenant context middleware
- A misconfigured reverse proxy routing requests to the wrong backend
- A report misidentification (user sees their own hospital's data but thinks it belongs elsewhere)

**Escalation path:**
1. Collect the exact API response (JSON) that contained the unexpected data.
2. Note the `X-Tenant-ID` that was sent with the request.
3. Note the `db_name` of the hospital whose data appeared.
4. Escalate immediately to MediFleet Support with both values — this requires code-level investigation.

---

### 4.3 New Tenant Not Appearing in Hospital Picker

**Severity**: Medium  
**Cause**: The tenant was created but `is_active` was not set to `TRUE`, or the provisioning process failed and was partially rolled back.

**Diagnostic steps:**
```sql
-- In hms_master
SELECT id, name, db_name, is_active, created_at FROM tenants ORDER BY created_at DESC LIMIT 10;
```

**If `is_active = FALSE`:**
```sql
UPDATE tenants SET is_active = TRUE WHERE db_name = 'new_hospital_db';
```

**If the tenant row exists but the database does not:**
```sql
-- Check if database was created
SELECT datname FROM pg_database WHERE datname = 'new_hospital_db';
```

If the database is missing, the provisioning failed. The master DB row cleanup is best-effort. You must either:
1. Re-run provisioning from the admin panel (Hospital Management → Add Hospital).
2. Manually clean up the orphaned `tenants` row and retry:
   ```sql
   DELETE FROM tenants WHERE db_name = 'new_hospital_db' AND is_active = FALSE;
   ```

**Tenant provisioning sequence (for reference):** CREATE DATABASE → schema migrations → RBAC setup → locations → settings → Admin user. If any step fails, the `tenants` row in `hms_master` is deleted (best-effort). If cleanup fails, an orphaned row may remain.

---

## Part 5: Deployment Issues

### 5.1 Docker Compose

#### Port 5432 Already in Use

**Symptom**: PostgreSQL container fails to start with `address already in use`.  
**Cause**: A PostgreSQL instance is already running on the host on port 5432.

**Fix — map to a different host port in `docker-compose.yml`:**
```yaml
services:
  postgres:
    ports:
      - "5433:5432"  # Map host port 5433 to container port 5432
```

Update `DATABASE_URL` in your `.env` to use port 5433:
```
DATABASE_URL=postgresql://user:pass@localhost:5433/hms_master
```

Or stop the conflicting host PostgreSQL:
```bash
sudo systemctl stop postgresql
```

---

#### Backend Container Exits Immediately

**Symptom**: `docker compose up` starts the backend container but it exits within seconds.

**Diagnostic steps:**
```bash
docker compose logs backend
```

**Common causes and fixes:**

| Log Output | Cause | Fix |
|------------|-------|-----|
| `DATABASE_URL is empty` | Missing env var | Add to `.env` or `docker-compose.yml` |
| `DATABASE_URL must start with postgresql://` | Wrong prefix | Normalize URL |
| `Connection refused` to postgres | Postgres not ready | Add `depends_on` with health check |
| `SECRET_KEY` missing | Missing env var | Add to `.env` |

**Recommended `docker-compose.yml` structure:**
```yaml
services:
  backend:
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://user:pass@postgres:5432/hms_master
      SECRET_KEY: your_secret_key
      REDIS_URL: redis://redis:6379/0
```

---

#### Migration Fails on First Boot

**Symptom**: Backend logs show migration errors during startup.  
**Cause**: `backend/render-start.sh` runs `python scripts/migrate_all_tenants.py` before starting uvicorn. If this script fails, uvicorn does not start.

**Diagnostic steps:**
```bash
docker compose logs backend | grep -E "(migrate|alembic|error|Error)"
```

**Common causes:**
- `hms_master` database does not exist yet (first run)
- Migration files have conflicts

**Fix for first run:**
```bash
# Manually create the master database
docker compose exec postgres psql -U postgres -c "CREATE DATABASE hms_master;"

# Then restart the backend
docker compose restart backend
```

---

### 5.2 Render.com

#### Build Failed (Incorrect Build Command)

**Symptom**: Render.com build step fails.  
**Cause**: Build command is set incorrectly in Render.com service settings.

**Correct build command for backend:**
```bash
pip install -r requirements.txt
```

**Correct start command:**
```bash
bash render-start.sh
```

The `render-start.sh` script handles migrations before starting uvicorn. Do not start uvicorn directly as the start command.

---

#### Backend Starts but `/api/` Routes Return 502

**Symptom**: The health check at `/api/` returns 502 Bad Gateway after a fresh deployment.  
**Cause**: Most likely the migration script (`migrate_all_tenants.py`) failed and the backend process exited. Render.com may briefly show the old deployment as live.

**Diagnostic steps:**
1. Go to Render.com dashboard → your Web Service → Logs.
2. Search for `"Auto-migrate finished with exit"` — if exit code is non-zero, migration failed.
3. Search for the specific error (e.g., `"Can't locate revision"`, `"Connection refused"`).

**Fix:**
- For migration failures, see Part 2.3.
- After fixing, trigger a manual deploy from the Render.com dashboard.

---

#### CORS Errors

**Symptom**: Browser console shows `"CORS policy: No 'Access-Control-Allow-Origin' header"`.  
**Cause**: `CORS_ORIGINS` environment variable does not include the frontend's origin.

**Fix:**
Set `CORS_ORIGINS` in Render.com environment variables:
```
CORS_ORIGINS=https://your-hospital.vercel.app,https://app.medifleet.io
```

Comma-separated, no trailing slash, exact scheme and host match required. A wildcard (`*`) is not suitable for production because the API uses credentials (cookies).

---

### 5.3 Vercel Frontend

#### API Calls Fail (VITE_API_URL Points to Localhost)

**Symptom**: All API calls in production fail with connection refused or network errors.  
**Cause**: `VITE_API_URL` was set to `http://localhost:8000` (development value) and baked into the production build.

**Fix:**
1. Go to Vercel → Project → Settings → Environment Variables.
2. Set `VITE_API_URL` to your production backend URL: `https://your-backend.onrender.com`
3. Redeploy (Settings → Deployments → Redeploy, or push a new commit).

---

#### Blank Page in Production (SPA Routing)

**Symptom**: The app loads at `/` but navigating directly to `/patients/123` or refreshing on any sub-route shows a blank page or 404.  
**Cause**: Vercel serves static files and doesn't know to route all paths to `index.html` for the React SPA router.

**Fix — create or update `vercel.json` in the frontend directory:**
```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

Commit and push. Vercel will redeploy automatically.

---

## Part 6: Logging Guide

### 6.1 Backend Log Locations

**Local development:**
```bash
# Logs go to stdout — visible directly in terminal
uvicorn app.main:app --reload
```

**Docker Compose:**
```bash
# All backend logs
docker compose logs -f backend

# Last 100 lines
docker compose logs --tail=100 backend

# Filter for errors
docker compose logs backend 2>&1 | grep -iE "(error|exception|critical|fail)"
```

**Render.com:**
1. Navigate to your Web Service in the Render.com dashboard.
2. Click "Logs" in the left sidebar.
3. Use the search box to filter by keyword.
4. Logs are retained for 7 days on the free tier; longer on paid plans.

---

### 6.2 Key Log Identifiers

| Log Fragment | Meaning | Action |
|---|---|---|
| `Auto-migrate completed cleanly` | All tenant migrations succeeded on startup | None — healthy startup |
| `Auto-migrate finished with exit 1` | Migration script failed; uvicorn may not start | Check migration errors above this line; see Part 2.3 |
| `Auto-resolved Ngrok Callback URL: https://...` | Sandbox M-Pesa callback URL detected via Ngrok | None — correct sandbox behavior |
| `REDIS_URL not configured. WebSocket broadcasts will not span workers.` | Redis not set; multi-worker real-time is degraded | Set `REDIS_URL`; see Part 2.6 |
| `Unhandled Exception on {method} {path}` | An unexpected Python exception occurred | Check the stack trace immediately following this line |
| `AUTH_ERROR` | Authentication or authorization failure logged | Note the user, tenant, and IP address; investigate if repeated |
| `Insufficient stock` | Inventory dispense attempted with no available stock | Check stock levels in the relevant tenant's pharmacy/inventory |
| `IdempotencyKey already exists` | A duplicate charge attempt was blocked | Expected behavior — no double charge occurred |
| `Cross-tenant refresh forbidden` | Refresh token used with wrong tenant header | Security event — see Part 2.2 |
| `Refresh token reuse detected` | Token replay attack or compromised token | Security event — see Part 8.3 |

---

### 6.3 Audit Log SQL Queries

The `audit_logs` table records every CREATE, UPDATE, and DELETE operation performed through the API. Columns: `user_id`, `action`, `entity_type`, `entity_id`, `old_value` (JSONB), `new_value` (JSONB), `ip_address`, `timestamp`.

**Query 1 — Recent writes by a specific user:**
```sql
-- Replace 42 with the actual user_id
SELECT action, entity_type, entity_id, ip_address, timestamp
FROM audit_logs
WHERE user_id = 42
ORDER BY timestamp DESC
LIMIT 50;
```
Use this to review what a specific staff member has done recently, e.g., during a dispute or disciplinary investigation.

**Query 2 — Full change history for a specific patient:**
```sql
-- Replace '123' with the actual patient entity_id
SELECT action, user_id, old_value, new_value, ip_address, timestamp
FROM audit_logs
WHERE entity_type = 'Patient' AND entity_id = '123'
ORDER BY timestamp;
```
Use this to reconstruct the full history of changes to a patient record, including what data was present before each change.

**Query 3 — All destructive actions today:**
```sql
SELECT user_id, entity_type, entity_id, old_value, ip_address, timestamp
FROM audit_logs
WHERE action = 'DELETE' AND timestamp >= CURRENT_DATE
ORDER BY timestamp DESC;
```
Use this for daily security review or when investigating data loss complaints.

---

### 6.4 Frontend Logs

**Browser DevTools Console:**
- Filter by `Error` to see JavaScript exceptions and failed fetch calls.
- Look for `401`, `403`, `402`, `422` status codes in red.
- React rendering errors appear with a component stack trace.

**DevTools Network Tab Analysis:**
1. Filter by "Fetch/XHR" to see API calls.
2. Click on a failing request → Preview tab to see the error JSON.
3. Check Request Headers for `X-Tenant-ID`, `x-csrf-token`, and `Cookie`.

**FastAPI HTTPException JSON shape:**
```json
{
  "detail": "Account locked. Try again in 12 minutes."
}
```

**Pydantic validation error JSON shape (HTTP 422):**
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email address",
      "type": "value_error.email"
    }
  ]
}
```

For 422 errors: the `loc` array tells you exactly which field failed validation. Pass this information to MediFleet Support if the field appears correct to the user.

---

### 6.5 PostgreSQL Query Log Configuration

To enable slow query logging for performance investigation, add or update the following in `postgresql.conf`:

```conf
# Log queries slower than 500ms
log_min_duration_statement = 500

# Log all connections (useful for pool debugging)
log_connections = on
log_disconnections = on

# Log lock waits
log_lock_waits = on
deadlock_timeout = 1s

# Where logs go
logging_collector = on
log_directory = 'pg_log'
log_filename = 'postgresql-%Y-%m-%d.log'
```

Apply changes:
```bash
# Reload config without full restart
psql -U postgres -c "SELECT pg_reload_conf();"
```

On Render.com managed Postgres, these settings may not be directly configurable. Contact Render.com support or use the `pg_stat_statements` extension for query analysis:
```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
SELECT query, calls, total_exec_time, mean_exec_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

---

## Part 7: Common Error Quick-Reference Table

| Symptom | HTTP Status | Most Likely Cause | Quick Fix |
|---------|------------|-------------------|-----------|
| `"DATABASE_URL is empty"` on startup | — (crash) | `DATABASE_URL` env var not set | Set `DATABASE_URL` in environment |
| `"DATABASE_URL must start with postgresql://"` | — (crash) | Render.com provides `postgres://` prefix | Replace `postgres://` with `postgresql://` |
| `"X-Tenant-ID header is required"` | 400 | Frontend not sending tenant header | Re-select hospital in picker; check tenant context persistence |
| `"Account locked. Try again in N minutes."` | 403 | 5 failed logins triggered 15-min lockout | Wait 15 min or reset via SQL |
| `"CSRF verification failed"` | 403 | Missing or mismatched CSRF token | Clear cookies, log in again; verify `CORS_ORIGINS` |
| `"Refresh token reuse detected — all sessions revoked"` | 401 | Token replay or compromised token | User must log in again; investigate per Part 8.3 |
| `"Cross-tenant refresh forbidden"` | 403 | Refresh token from Tenant A used for Tenant B | Clear cookies, log in again |
| `"Invalid or already-used reset token"` | 400 | Password reset link already used or expired | Request new password reset |
| `"relation X does not exist"` | 500 | Alembic migration not run for this tenant DB | Run `python scripts/migrate_all_tenants.py` |
| HTTP 402 `"Module Unavailable"` | 402 | Feature flag not enabled for tenant | Update `feature_flags` in `tenants` table; 60s cache TTL |
| `"M-Pesa is not configured or is inactive."` | 400 | No active `MpesaConfig` for tenant | Enable in admin panel or set `is_active = TRUE` |
| `"Failed to authenticate with Safaricom Daraja API"` | 502 | Invalid M-Pesa consumer key/secret | Re-enter credentials via admin panel; test with curl |
| `"The balance is insufficient"` | 200 (callback) | Customer's M-Pesa balance too low | Inform patient; offer alternative payment |
| `"Request cancelled by user"` | 200 (callback) | Customer dismissed STK push | Offer to resend STK push |
| `"REDIS_URL not configured"` | — (warning) | Redis env var missing | Set `REDIS_URL`; real-time works but not multi-worker |
| `"Insufficient stock"` | 400 | Stock batch quantity depleted | Check stock levels; receive new stock batch |
| WebSocket 404 or no upgrade | — | Nginx missing `Upgrade`/`Connection` headers | Add WebSocket proxy headers to nginx config |
| Dashboard slow (3–8s) | 200 | Redis down; queries hit DB directly | Restore Redis |
| Patient search slow | 200 | Missing pg_trgm index | Create trigram index on `patients.full_name` |
| Blank page on direct URL in production | — | SPA routes not rewritten to `index.html` | Add `vercel.json` rewrite rule |
| CORS error in browser console | — | Frontend origin not in `CORS_ORIGINS` | Add frontend URL to `CORS_ORIGINS` env var |
| 502 on Render.com after deploy | 502 | Migration failed; uvicorn didn't start | Check logs for `Auto-migrate finished with exit 1` |

---

## Part 8: Security Incident Response

### 8.1 Suspected Unauthorized Access

Follow these steps in order. Document each action with timestamp.

**Step 1 — Immediate containment:**
```sql
-- Deactivate the suspected account (in the relevant tenant database)
UPDATE users SET is_active = FALSE WHERE email = 'compromised@example.com';
```

**Step 2 — Revoke all sessions:**
```sql
-- Revoke all active sessions for the user
UPDATE refresh_tokens
SET revoked = TRUE
WHERE user_id = (SELECT user_id FROM users WHERE email = 'compromised@example.com');
```

**Step 3 — Review recent activity in audit logs:**
```sql
-- Find the user_id first
SELECT user_id, email FROM users WHERE email = 'compromised@example.com';

-- Then review all actions in the last 24 hours
SELECT action, entity_type, entity_id, old_value, new_value, ip_address, timestamp
FROM audit_logs
WHERE user_id = <user_id>
  AND timestamp >= NOW() - INTERVAL '24 hours'
ORDER BY timestamp;
```

**Step 4 — Check login history and IP addresses:**
```sql
-- Look for unusual IP addresses
SELECT DISTINCT ip_address, MIN(timestamp) as first_seen, MAX(timestamp) as last_seen, COUNT(*) as requests
FROM audit_logs
WHERE user_id = <user_id>
  AND timestamp >= NOW() - INTERVAL '7 days'
GROUP BY ip_address
ORDER BY last_seen DESC;
```

**Step 5 — Determine breach scope:**
- Did the user access patient records they should not have accessed?
- Did any data leave the system (e.g., bulk exports)?
- Were any other accounts created or modified?
- Were any audit log entries deleted? (Audit logs should be append-only; deletion is itself an indicator of compromise.)

**Step 6 — Escalate and document:**
- Notify your hospital's Data Protection Officer.
- If patient data was accessed without authorization, proceed to Part 8.2 (KDPA Breach Response).
- Escalate to MediFleet Support with your findings.

---

### 8.2 KDPA Breach Response Checklist

Kenya Data Protection Act (2019), Section 43 requires notification to the Office of the Data Protection Commissioner (ODPC) within 72 hours of becoming aware of a personal data breach.

**Create a BreachIncident record immediately. Required fields:**

| Field | Description | Example |
|-------|-------------|---------|
| `incident_date` | When the breach occurred (best estimate) | `2026-05-16 10:30:00` |
| `discovery_date` | When staff became aware of it | `2026-05-16 11:00:00` |
| `description` | What happened — clear, factual, no speculation | `"Staff account credentials compromised; unauthorized access to patient records in ward A"` |
| `data_categories` | Types of data affected | `["name", "diagnosis", "contact"]` |
| `affected_count` | Number of patients/data subjects affected (estimate if unknown) | `47` |
| `severity` | Low / Medium / High / Critical | Based on sensitivity and scope |
| `containment_actions` | What was done immediately | `"Account deactivated, sessions revoked, password reset required"` |
| `reporter_id` | User ID of the staff member logging the incident | Your user ID |
| `status` | Current status | See progression below |

**Status progression:**
1. `Open` — Incident created; investigation not yet started.
2. `Investigating` — Root cause analysis underway.
3. `Contained` — Breach stopped; no further unauthorized access possible.
4. `Closed` — Full investigation complete; ODPC notified if required; patients notified if required.

**72-hour ODPC notification checklist (S.43):**
- [ ] Incident discovered and documented (start 72-hour clock)
- [ ] BreachIncident record created with all known fields
- [ ] Scope of breach determined (categories, count, sensitivity)
- [ ] Preliminary notification sent to ODPC at odpc.go.ke if breach involves personal data
- [ ] Notification includes: nature of breach, categories and approximate number of data subjects, contact details of DPO, likely consequences, measures taken or proposed
- [ ] If full details not available within 72h, provide what is known and follow up

**Patient notification requirement:**
If the breach is likely to result in high risk to the rights and freedoms of data subjects (e.g., health data exposed), patients must be notified directly without undue delay. The notification must:
- Describe the nature of the breach in plain language
- Name and contact details of your Data Protection Officer
- Describe the likely consequences
- Describe the measures taken to address the breach

---

### 8.3 Refresh Token Reuse Detection

**What happened:**
The system detected that a refresh token which had already been used and rotated was submitted again. Under the token rotation scheme, each refresh token is single-use — when used, it is revoked and a new one is issued. Resubmitting a used token is a security event indicating one of:

1. A token was intercepted in transit (MITM attack) and replayed by an attacker.
2. A client implementation bug is retrying a request that already succeeded.
3. A stolen token (e.g., from a compromised device) is being used.

**What the system already did:**
ALL refresh tokens for the affected user were immediately revoked. The user's active session was terminated. They received `"Refresh token reuse detected — all sessions revoked"` (HTTP 401). The event is logged.

**What you must do next:**

**Step 1 — Notify the user:**
Contact the user through an out-of-band channel (email or phone — not through the system, as it may be compromised). Inform them:
- Their account session was terminated due to a security event.
- They must log in again.
- They should change their password immediately after logging in.

**Step 2 — Investigate the token's origin:**
```sql
-- Review the user's recent session and IP history
SELECT ip_address, timestamp
FROM audit_logs
WHERE user_id = <user_id>
  AND timestamp >= NOW() - INTERVAL '48 hours'
ORDER BY timestamp DESC;
```

Look for IP addresses that don't match the user's known locations or devices.

**Step 3 — Determine if it was a client bug or a real attack:**
- If the IP addresses all look legitimate and the user reports no suspicious activity: likely a client retry bug. Document and monitor.
- If there are unknown IPs or the user reports they did not initiate those sessions: treat as a stolen token. Proceed to Part 8.1 (Suspected Unauthorized Access) and assess for KDPA breach.

**Step 4 — Document the event:**
Log the incident in your security event register regardless of whether it was a bug or attack. Include the user ID, timestamp, IP addresses observed, and conclusion.

**Step 5 — Monitor for recurrence:**
If this happens repeatedly for the same user without explanation, escalate to MediFleet Support — it may indicate a systemic vulnerability in token handling.
