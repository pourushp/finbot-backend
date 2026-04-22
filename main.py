import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import stocks, crypto, commodities, portfolio, news, mutual_funds, ai_chat

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

app.include_router(stocks.router, prefix="/api/stocks", tags=["Stocks"])
app.include_router(crypto.router, prefix="/api/crypto", tags=["Crypto"])
app.include_router(commodities.router, prefix="/api/commodities", tags=["Commodities"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(news.router, prefix="/api/news", tags=["News"])
app.include_router(mutual_funds.router, prefix="/api