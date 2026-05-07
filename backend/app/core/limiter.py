from slowapi import Limiter
from slowapi.util import get_remote_address

# Global Rate Limiter instance.
#
# `default_limits` apply a baseline to every endpoint by IP, so an authenticated
# bot can't flood data-heavy reads (patient search, inventory, lab queue, etc.).
# Endpoints with stricter explicit `@limiter.limit("...")` decorators (login,
# refresh, password reset) override this default.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute", "2000/hour"],
)
