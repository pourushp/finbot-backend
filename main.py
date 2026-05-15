import os
import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import stocks, crypto, commodities, portfolio, news, mutual_funds, ai_chat, user_data
from middleware import RateLimitMiddleware

# Sentry error monitoring (optional — set SENTRY_DSN env var)
sentry_dsn = os.getenv("SENTRY_DSN", "")
if sentry_dsn:
    sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0.1, profiles_sample_rate=0.1)

app = FastAPI(
    title="Financial Personal Assistant API",
    description="India-focused financial data, portfolio analytics, and AI assistant",
    version="1.0.0",
)

# Allow GitHub Pages frontend + local dev origins
allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "https://sent-i-meter.com",
    "https://www.sent-i-meter.com",
]

# Add production frontend URL from environment variable if set
frontend_url = os.environ.get("FRONTEND_URL", "")
if frontend_url:
    allowed_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

app.include_router(stocks.router, prefix="/api/stocks", tags=["Stocks"])
app.include_router(crypto.router, prefix="/api/crypto", tags=["Crypto"])
app.include_router(commodities.router, prefix="/api/commodities", tags=["Commodities"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(news.router, prefix="/api/news", tags=["News"])
app.include_router(mutual_funds.router, prefix="/api/mf", tags=["Mutual Funds"])
app.include_router(ai_chat.router, prefix="/api/ai", tags=["AI Assistant"])
app.include_router(user_data.router, prefix="/api/user", tags=["User Data"])


@app.get("/")
def root():
    return {"status": "ok", "message": "Financial Personal Assistant API v1.0"}


@app.get("/health")
def health():
    return {"status": "healthy"}
