"""Production middleware — rate limiting, request logging."""
import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# Simple in-memory rate limiter (upgrade to Redis/Upstash for production at scale)
_rate_store = defaultdict(list)
RATE_LIMIT = 60  # requests per window
RATE_WINDOW = 60  # seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ("/", "/health"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Clean old entries
        _rate_store[client_ip] = [t for t in _rate_store[client_ip] if now - t < RATE_WINDOW]

        if len(_rate_store[client_ip]) >= RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

        _rate_store[client_ip].append(now)

        # Add timing header
        start = time.time()
        response = await call_next(request)
        response.headers["X-Response-Time"] = f"{(time.time() - start) * 1000:.0f}ms"
        return response
