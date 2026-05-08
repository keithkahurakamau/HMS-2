import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import secrets
from app.core.limiter import limiter
from app.core.websocket import manager as ws_manager

from app.config.settings import settings

# Absolute path imports enforcing modular monolith architecture
import app.auth.auth as auth_module
import app.routes.dashboard as dashboard_module
import app.routes.patients as patients_module
import app.routes.appointments as appointments_module
import app.routes.queue as queue_module
import app.routes.clinical as clinical_module
import app.routes.laboratory as laboratory_module
import app.routes.pharmacy as pharmacy_module
import app.routes.inventory as inventory_module
import app.routes.wards as wards_module
import app.routes.billing as billing_module
import app.routes.users as users_module
import app.routes.admin as admin_module
import app.routes.analytics as analytics_module
import app.routes.websockets as websockets_module
import app.routes.radiology as radiology_module
import app.routes.medical_history as medical_history_module
import app.routes.public as public_module
import app.routes.mpesa_admin as mpesa_admin_module
import app.routes.mpesa_payment as mpesa_payment_module
import app.routes.privacy as privacy_module
import app.routes.notifications as notifications_module
import app.routes.patient_portal as patient_portal_module
import app.routes.messaging as messaging_module

# 1. Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. Setup SlowAPI Rate Limiter (Imported from app.core.limiter)

# 3. Initialize FastAPI Application
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Boot: warm up the WebSocket Redis backend if configured.
    await ws_manager.init_redis()
    if not settings.REDIS_URL:
        logger.warning("REDIS_URL not configured. WebSocket broadcasts will not span workers.")
    try:
        yield
    finally:
        await ws_manager.shutdown()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Enterprise Hospital Management System API",
    lifespan=lifespan,
)

# 4. Attach Rate Limiter to App.
# SlowAPIMiddleware applies the limiter's default_limits globally to every route,
# so unauthenticated bots cannot flood data-heavy reads. Routes with explicit
# `@limiter.limit("...")` decorators still get their stricter per-route limits.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# 5. Configure CORS (Must be added BEFORE custom http middlewares)
# Allowed origins are sourced from settings.CORS_ORIGINS so production deployments
# can lock the list down to a closed set of trusted domains via the environment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 6. Global Middleware: Process Time (Removed Exception Catcher from here)
@app.middleware("http")
async def process_time_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# 6b. CSRF Protection Middleware
@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    # Set CSRF cookie for safe methods if missing
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        response = await call_next(request)
        if not request.cookies.get("csrf_token"):
            is_production = settings.MPESA_ENV.lower() == "production"
            response.set_cookie(
                "csrf_token", 
                secrets.token_hex(32), 
                httponly=False, 
                secure=is_production, 
                samesite="none" if is_production else "lax"
            )
        return response
    
    # Exclude login and webhooks/public endpoints from CSRF check.
    # The public router lives under /api/public (the prior /public prefix was a
    # typo that left the superadmin login unreachable from a fresh tab).
    if (
        request.url.path.startswith("/api/auth/login")
        or request.url.path.startswith("/api/public/")
    ):
        return await call_next(request)

    # Validate Double Submit Cookie for state-changing methods
    csrf_cookie = request.cookies.get("csrf_token")
    csrf_header = request.headers.get("x-csrf-token")
    
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        return JSONResponse(
            status_code=403, 
            content={"detail": "CSRF verification failed. Missing or invalid token."}
        )
        
    return await call_next(request)

# 7. Proper Global Exception Handler (Preserves CORS headers)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. System operators have been notified."},
    )

# 8. Include API Routers
app.include_router(auth_module.router)
app.include_router(dashboard_module.router)
app.include_router(users_module.router)
app.include_router(admin_module.router)
app.include_router(patients_module.router)
app.include_router(appointments_module.router)
app.include_router(queue_module.router)
app.include_router(clinical_module.router)
app.include_router(laboratory_module.router)
app.include_router(pharmacy_module.router)
app.include_router(inventory_module.router)
app.include_router(wards_module.router)
app.include_router(billing_module.router)
app.include_router(analytics_module.router)
app.include_router(websockets_module.router)
app.include_router(radiology_module.router)
app.include_router(medical_history_module.router)
app.include_router(public_module.router)
app.include_router(mpesa_admin_module.router)
app.include_router(mpesa_payment_module.router)
app.include_router(privacy_module.router)
app.include_router(notifications_module.router)
app.include_router(patient_portal_module.router)
app.include_router(messaging_module.router)

# 9. Health Check Route
@app.get("/")
def root():
    return {
        "system": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "Operational",
        "timestamp": time.time()
    }