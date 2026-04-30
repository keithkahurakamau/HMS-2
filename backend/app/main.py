import time
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config.settings import settings

# Absolute path imports enforcing modular monolith architecture
import app.routes.auth as auth_module
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

# 1. Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 2. Setup SlowAPI Rate Limiter
limiter = Limiter(key_func=get_remote_address)

# 3. Initialize FastAPI Application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Enterprise Hospital Management System API"
)

# 4. Attach Rate Limiter to App
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 5. Configure CORS (Must be added BEFORE custom http middlewares)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    
        "http://127.0.0.1:5173",    
        "http://localhost:3000",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app", 
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

# 9. Health Check Route
@app.get("/")
def root():
    return {
        "system": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "Operational",
        "timestamp": time.time()
    }