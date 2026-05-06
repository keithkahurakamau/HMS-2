from slowapi import Limiter
from slowapi.util import get_remote_address

# Global Rate Limiter instance
limiter = Limiter(key_func=get_remote_address)
