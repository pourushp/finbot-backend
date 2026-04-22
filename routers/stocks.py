from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

router = APIRouter()

# Major Indian indices
INDIAN_INDICES = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY IT": "^CNXIT",
    "NIFTY MIDCAP 100": "NIFTYMIDCAP100.NS",
    "NIFTY SMALLCAP 100": "^CNXSC",
}

# Popular NSE stocks for quick access
POPULAR_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BAJFINANCE.NS", "BHARTIARTL.NS",
    "WIPRO.NS", "AXISBANK.NS", "MARUTI.NS", "TITAN.NS", "SUNPHARMA.NS",
]


def safe_float(val):
    """Convert to float, return None if not possible."""
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def ticker_info_to_dict(ticker_sym: str) -> dict:
    """Fetch basic quote info for a single symbol."""
    try:
        t = yf.Ticker(ticker_sym)
        info = t.fast_info
        hist = t.history(period="2d")
        if hist.empty:
            return None
        latest = hist.iloc[-1]
        prev = hist.iloc[-2] if len(hist) > 1 else hist.iloc[-1]
        change = latest["Close"] - prev["Close"]
        change_pct = (change / prev["Close"]) * 100 if prev["Close"] else 0

        return {
            "symbol": ticker_sym,
            "price": safe_float(latest["Close"]),
            "open": safe_float(latest["Open"]),
            "high": safe_float(latest["High"]),
            "low": safe_float(latest["Low"]),
            "volume": safe_float(latest["Volume"]),
            "change": safe_float(change),
            "change_pct": safe_float(change_pct),
            "market_cap": safe_float(getattr(info, "market_cap", None)),
            "currency": getattr(info, "currency", "INR"),
        }
    except Exception as e:
        return None


@router.get("/indices")
def get_indices():
    """Get all major Indian market indices."""
    results = []
    for name, symbol in INDIAN_INDICES.items():
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period="2d")
            if hist.empty:
                continue
            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else hist.iloc[-1]
            change = latest["Close"] - prev["Close"]
            change_pct = (change / prev["Close"]) * 100 if prev["Close"] else 0
            results.append({
                "name": name,
                "symbol": symbol,
                "price": safe_float(latest["Close"]),
                "change": safe_float(change),
                "change_pct": safe_float(change_pct),
                "high": safe_float(latest["High"]),
                "low": safe_float(latest["Low"]),
            })
        except Exception:
            continue
    return results


@router.get("/search")
def search_stocks(q: str = Query(..., description="Search query (company name or symbol)")):
    """Search for stocks by name or symbol. Appends .NS for Indian stocks."""
    query = q.strip().upper()
    candidates = []

    # Try direct symbol first
    for suffix in [".NS", ".BO", ""]:
        sym = query + suffix
        try:
            t = yf.Ticker(sym)
            info = t.fast_info
            hist = t.history(period="1d")
            if not hist.empty:
                candidates.append({
                    "symbol": sym,
                    "name": getattr(info, "exchange", sym),
                    "exchange": "NSE" if suffix == ".NS" else ("BSE" if suffix == ".BO" else "Global"),
                    "price": safe_float(hist.iloc[-1]["Close"]),
                    "currency": getattr(info, "currency", "INR"),
                })
        except Exception:
            continue

    # Fuzzy match from popular list
    for sym in POPULAR_STOCKS:
        if query in sym and sym not in [c["symbol"] for c in candidates]:
            data = ticker_info_to_dict(sym)
            if data:
                data["exchange"] = "NSE"
                candidates.append(data)

    return candidates[:10]


@router.get("/quote")
def get_quotes(symbols: str = Query(..., description="Comma-separated symbols e.g. RELIANCE.NS,TCS.NS")):
    """Get current quotes for multiple symbols."""
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    results = []
    for sym in syms:
        data = ticker_info_to_dict(sym)
        if data:
            results.append(data)
    return results


@router.get("/historical/{symbol}")
def get_historical(
    symbol: str,
    period: str = Query("1y", description="1mo, 3mo, 6mo, 1y, 2y, 5y"),
    interval: str = Query("1d", description="1d, 1wk, 1mo"),
):
    """Get historical OHLCV data for a symbol."""
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period=period, interval=interval)
        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
        hist = hist.reset_index()
        records = []
        for _, row in hist.iterrows():
            date_val = row["Date"]
            if hasattr(date_val, "isoformat"):
                date_str = date_val.isoformat()
            else:
                date_str = str(date_val)
            records.append({
                "date": date_str[:10],
                "open": safe_float(row["Open"]),
                "high": safe_float(row["High"]),
                "low": safe_float(row["Low"]),
                "close": safe_float(row["Close"]),
                "volume": safe_float(row["Volume"]),
            })
        return {"symbol": symbol, "period": period, "interval": interval, "data": records}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/earnings/{symbol}")
def get_earnings(symbol: str):
    """Get quarterly earnings (EPS + revenue) for a stock."""
    try:
        t = yf.Ticker(symbol)
        quarterly = t.quarterly_financials
        quarterly_income = t.quarterly_income_stmt
        eps_data = t.quarterly_earnings

        result = {"symbol": symbol, "quarterly": []}

        if quarterly_income is not None and not quarterly_income.empty:
            df = quarterly_income.T
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

            for date, row in df.iterrows():
                entry = {
                    "quarter": date.strftime("%b %Y"),
                    "date": date.strftime("%Y-%m-%d"),
                    "revenue": safe_float(row.get("Total Revenue")),
                    "gross_profit": safe_float(row.get("Gross Profit")),
                    "operating_income": safe_float(row.get("Operating Income")),
                    "net_income": safe_float(row.get("Net Income")),
                    "ebitda": safe_float(row.get("EBITDA")),
                }
                result["quarterly"].append(entry)

        # Add EPS data if available
        if eps_data is not None and not eps_data.empty:
            eps_data = eps_data.reset_index()
            for _, row in eps_data.iterrows():
                q_str = str(row.get("Date", ""))
                for entry in result["quarterly"]:
                    if q_str[:7] == entry["date"][:7]:
                        entry["eps"] = safe_float(row.get("Earnings"))
                        entry["eps_estimated"] = safe_float(row.get("EPS Estimate", None))

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/earnings-batch")
def get_earnings_batch(symbols: str = Query(..., description="Comma-separated symbols")):
    """Get quarterly earnings for multiple symbols (from uploaded CSV)."""
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    results = []
    for sym in syms:
        try:
            data = get_earnings(sym)
            results.append(data)
        except Exception:
            results.append({"symbol": sym, "quarterly": [], "error": "Data unavailable"})
    return results


@router.get("/movers")
def get_top_movers():
    """Get top gainers and losers from NSE."""
    results = []
    for sym in POPULAR_STOCKS:
        data = ticker_info_to_dict(sym)
        if data:
            results.append(data)

    gainers = sorted([r for r in results if r.get("change_pct", 0) > 0],
                     key=lambda x: x.get("change_pct", 0), reverse=True)[:5]
    losers = sorted([r for r in results if r.get("change_pct", 0) < 0],
                    key=lambda x: x.get("change_pct", 0))[:5]
    return {"gainers": gainers, "losers": losers}
