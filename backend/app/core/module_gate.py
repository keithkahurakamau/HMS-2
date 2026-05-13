"""
Module-entitlement middleware.

Sits in the FastAPI middleware stack between CSRF and the route handlers.
For each tenant-scoped request, it:

  1. Maps the URL path to a module key (see :mod:`app.core.modules`).
  2. Looks up the tenant's entitlement cache (~60s TTL backed by Redis).
  3. If the resolved module is disabled, short-circuits with **HTTP 402
     Payment Required** and a structured payload the frontend renders as a
     full-page upgrade card.

Design notes:
  * Paths outside ``/api/`` (frontend assets, websockets, health checks) are
    passed through untouched.
  * Anything under ``/api/public/`` is unconditionally allowed — that
    surface authenticates per-route (login, superadmin) and is the only way
    a locked-out tenant can recover.
  * If the ``X-Tenant-ID`` header is missing we let the request through;
    the downstream :func:`app.config.database.get_db` will produce its own
    400 with a clearer message. Coupling two gates would just confuse
    callers.
  * The 402 payload mirrors FastAPI's ``HTTPException`` shape so existing
    axios interceptors don't break, but includes a ``module`` block that
    the frontend uses to render the upgrade prompt and pre-fill the
    support ticket.
"""
from __future__ import annotations

import logging

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.modules import (
    ALWAYS_ON,
    BY_KEY,
    get_tenant_flags_cached,
    is_module_enabled,
    url_to_module,
)

logger = logging.getLogger(__name__)


class ModuleGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Cheap early-outs first — most traffic should skip the lookup.
        if not path.startswith("/api/") or path.startswith("/api/public/"):
            return await call_next(request)

        module = url_to_module(path)
        if module is None or module in ALWAYS_ON:
            return await call_next(request)

        tenant_db = request.headers.get("X-Tenant-ID")
        if not tenant_db:
            # Let get_db produce the 400 — see docstring above.
            return await call_next(request)

        flags_raw = get_tenant_flags_cached(tenant_db)
        if is_module_enabled(flags_raw, module):
            return await call_next(request)

        mod_def = BY_KEY.get(module)
        label = mod_def.label if mod_def else module
        payload = {
            "detail": f"The {label} module is not included in your package.",
            "module": {
                "key": module,
                "label": label,
                "reason": "not_in_plan",
                # Frontend reads contact_action to know which support ticket
                # category and subject to pre-fill on the upgrade page.
                "contact_action": {
                    "kind": "support_ticket",
                    "category": "Account",
                    "subject": f"Upgrade request: {label}",
                    "support_path": "/app/support",
                },
                "message": (
                    f"Contact MediFleet Support to upgrade your package and "
                    f"unlock {label}."
                ),
            },
        }
        return JSONResponse(status_code=402, content=payload)
