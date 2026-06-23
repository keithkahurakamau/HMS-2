/*
 * MediFleet backend load test (k6)
 * =================================
 *
 * Measures the two throughput ceilings discussed in the capacity review:
 *   1. `reads`  — steady authenticated JSON reads (the everyday workload).
 *   2. `login`  — a login storm that stresses Argon2id (the shift-change risk;
 *                 ~80 ms CPU + 64 MiB RAM per hash on a 512 MB Render Starter).
 *
 * Auth model: the API is cookie-based (HttpOnly access/refresh cookies set by
 * POST /api/auth/login). k6 keeps a per-VU cookie jar automatically, so a VU
 * logs in once and reuses the session for subsequent reads. Every authenticated
 * request must carry the X-Tenant-ID header matching the token's tenant.
 *
 * ── Quick start ───────────────────────────────────────────────────────────
 *   # install k6: https://grafana.com/docs/k6/latest/set-up/install-k6/
 *
 *   # steady-read capacity (default scenario):
 *   k6 run \
 *     -e BASE_URL=https://your-api.onrender.com \
 *     -e TENANT_ID=mayoclinic_db \
 *     -e EMAIL=admin@mayoclinic.hms.co.ke \
 *     -e PASSWORD='...' \
 *     scripts/loadtest/k6-load-test.js
 *
 *   # login storm (see the rate-limit note below):
 *   k6 run -e SCENARIO=login -e BASE_URL=... -e TENANT_ID=... \
 *     -e EMAIL=... -e PASSWORD=... scripts/loadtest/k6-load-test.js
 *
 *   # both at once:
 *   k6 run -e SCENARIO=both ... scripts/loadtest/k6-load-test.js
 *
 * ── IMPORTANT: the login rate limit ────────────────────────────────────────
 * /api/auth/login is capped at 5/min PER IP (core/limiter.py). A login storm
 * from a single machine therefore measures the rate limiter, not Argon2
 * capacity — you'll see 429s almost immediately (counted as `rate_limited`,
 * which is EXPECTED, not a failure). To measure true login capacity, run against
 * a STAGING deploy with the per-route login limit raised/removed, or distribute
 * the test across many source IPs (k6 Cloud / multiple agents).
 *
 * ── Tuning (all optional, via -e) ──────────────────────────────────────────
 *   SCENARIO       reads | login | both           (default: reads)
 *   READ_TARGET_RPS   peak requests/sec for reads (default: 20)
 *   READ_RAMP         ramp+hold duration          (default: 1m per stage)
 *   LOGIN_TARGET_RPS  peak login attempts/sec     (default: 5)
 *   READ_PATHS     comma-separated GET paths to rotate through
 *                  (default: dashboard agenda, notifications, patients list)
 *   P95_MS         p95 latency threshold in ms     (default: 1500)
 *   ERROR_RATE     max non-rate-limited error rate (default: 0.01 = 1%)
 */
import http from 'k6/http';
import { check, fail } from 'k6';
import { Counter, Trend } from 'k6/metrics';

// ── Config from environment ────────────────────────────────────────────────
const BASE_URL = (__ENV.BASE_URL || '').replace(/\/$/, '');
const TENANT_ID = __ENV.TENANT_ID || '';
const EMAIL = __ENV.EMAIL || '';
const PASSWORD = __ENV.PASSWORD || '';
const SCENARIO = (__ENV.SCENARIO || 'reads').toLowerCase();

const READ_TARGET_RPS = parseInt(__ENV.READ_TARGET_RPS || '20', 10);
const LOGIN_TARGET_RPS = parseInt(__ENV.LOGIN_TARGET_RPS || '5', 10);
const READ_RAMP = __ENV.READ_RAMP || '1m';
const P95_MS = parseInt(__ENV.P95_MS || '1500', 10);
const ERROR_RATE = parseFloat(__ENV.ERROR_RATE || '0.01');

const READ_PATHS = (__ENV.READ_PATHS
  || '/api/dashboard/worker-agenda,/api/notifications/,/api/patients/'
).split(',').map((p) => p.trim()).filter(Boolean);

// ── Custom metrics ─────────────────────────────────────────────────────────
const loginDuration = new Trend('login_duration', true);
const loginOk = new Counter('login_ok');
const rateLimited = new Counter('rate_limited'); // 429s — expected on login storm
const authedReads = new Counter('authed_reads');

// ── Scenario wiring ────────────────────────────────────────────────────────
function buildScenarios() {
  const s = {};
  if (SCENARIO === 'reads' || SCENARIO === 'both') {
    s.reads = {
      executor: 'ramping-arrival-rate',
      exec: 'browseAsStaff',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: Math.max(20, READ_TARGET_RPS * 2),
      maxVUs: Math.max(50, READ_TARGET_RPS * 5),
      stages: [
        { target: READ_TARGET_RPS, duration: READ_RAMP }, // ramp up
        { target: READ_TARGET_RPS, duration: READ_RAMP }, // hold at peak
        { target: 0, duration: '15s' },                   // ramp down
      ],
    };
  }
  if (SCENARIO === 'login' || SCENARIO === 'both') {
    s.login = {
      executor: 'ramping-arrival-rate',
      exec: 'loginStorm',
      startRate: 1,
      timeUnit: '1s',
      preAllocatedVUs: Math.max(10, LOGIN_TARGET_RPS * 2),
      maxVUs: Math.max(20, LOGIN_TARGET_RPS * 4),
      stages: [
        { target: LOGIN_TARGET_RPS, duration: READ_RAMP },
        { target: LOGIN_TARGET_RPS, duration: READ_RAMP },
        { target: 0, duration: '15s' },
      ],
      startTime: SCENARIO === 'both' ? '5s' : '0s',
    };
  }
  return s;
}

export const options = {
  scenarios: buildScenarios(),
  thresholds: {
    // Count only genuine errors (5xx / unexpected) against the SLO — 429s from
    // the deliberate login rate limit are tracked separately in `rate_limited`.
    http_req_failed: [`rate<${ERROR_RATE}`],
    http_req_duration: [`p(95)<${P95_MS}`],
    login_duration: [`p(95)<${Math.max(P95_MS, 2000)}`],
  },
  // Don't let one slow endpoint mask others.
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

// ── setup(): validate config + creds once, fail fast with a clear message ───
export function setup() {
  if (!BASE_URL) fail('BASE_URL is required (e.g. -e BASE_URL=https://your-api.onrender.com)');
  const needsAuth = SCENARIO !== 'noauth';
  if (needsAuth && (!TENANT_ID || !EMAIL || !PASSWORD)) {
    fail('TENANT_ID, EMAIL and PASSWORD are required for authenticated scenarios.');
  }
  // Probe the health route — confirms BASE_URL is live before we ramp.
  const health = http.get(`${BASE_URL}/`, { tags: { name: 'health' } });
  check(health, { 'health 200': (r) => r.status === 200 })
    || fail(`Health check failed at ${BASE_URL}/ (status ${health.status}). Check BASE_URL.`);

  // Validate creds once so a typo doesn't produce a wall of 401s.
  const res = login();
  if (res.status !== 200) {
    fail(`setup login failed (status ${res.status}). Check TENANT_ID/EMAIL/PASSWORD. Body: ${String(res.body).slice(0, 200)}`);
  }
  return { ok: true };
}

// ── Helpers ────────────────────────────────────────────────────────────────
function login() {
  const res = http.post(
    `${BASE_URL}/api/auth/login`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    {
      headers: { 'Content-Type': 'application/json', 'X-Tenant-ID': TENANT_ID },
      tags: { name: 'POST /api/auth/login' },
    },
  );
  loginDuration.add(res.timings.duration);
  if (res.status === 200) loginOk.add(1);
  if (res.status === 429) rateLimited.add(1);
  return res;
}

// Per-VU session flag — k6 gives each VU its own JS runtime + cookie jar, so
// this persists across a VU's iterations and is isolated between VUs.
let loggedIn = false;
let pathIdx = 0;

// ── reads scenario ─────────────────────────────────────────────────────────
export function browseAsStaff() {
  if (!loggedIn) {
    const res = login();
    // If we got rate-limited while logging in, back off this iteration.
    if (res.status === 429) return;
    loggedIn = res.status === 200;
    if (!loggedIn) return;
  }

  // Rotate through the configured read endpoints to spread DB load.
  const path = READ_PATHS[pathIdx % READ_PATHS.length];
  pathIdx += 1;
  const res = http.get(`${BASE_URL}${path}`, {
    headers: { 'X-Tenant-ID': TENANT_ID },
    tags: { name: `GET ${path}` },
  });
  authedReads.add(1);
  check(res, {
    'read ok (2xx)': (r) => r.status >= 200 && r.status < 300,
  });
  // A 401 means our session expired (15-min access token) — re-login next loop.
  if (res.status === 401) loggedIn = false;
}

// ── login storm scenario ───────────────────────────────────────────────────
export function loginStorm() {
  const res = login();
  // 200 = served, 429 = rate-limited (EXPECTED from a single IP, see header).
  check(res, {
    'login handled (200 or 429)': (r) => r.status === 200 || r.status === 429,
  });
}
