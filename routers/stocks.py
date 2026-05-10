from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
import requests
import time
import re
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

router = APIRouter()

# --- Simple in-memory cache ---
_cache = {}
CACHE_TTL = 120  # seconds

def _get_cached(key):
    if key in _cache:
        val, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return val
    return None

def _set_cached(key, val):
    _cache[key] = (val, time.time())

# --- NSE Session Management ---
_nse_session = None
_nse_session_ts = 0

NSE_BASE = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

def _get_nse_session():
    global _nse_session, _nse_session_ts
    if _nse_session and time.time() - _nse_session_ts < 120:
        return _nse_session
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    try:
        s.get(NSE_BASE, timeout=10)
    except Exception:
        pass
    _nse_session = s
    _nse_session_ts = time.time()
    return s

def _nse_fetch(path):
    try:
        s = _get_nse_session()
        r = s.get(f"{NSE_BASE}{path}", timeout=10)
        if r.status_code in (401, 403):
            global _nse_session_ts
            _nse_session_ts = 0
            s = _get_nse_session()
            r = s.get(f"{NSE_BASE}{path}", timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None
# --- Google Finance ---
def _google_finance_quote(symbol, exchange="NSE"):
    try:
        url = f"https://www.google.com/finance/quote/{symbol}:{exchange}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            return None
        text = r.text
        price_match = re.search(r'data-last-price="([^"]+)"', text)
        prev_match = re.search(r'data-previous-close="([^"]+)"', text)
        if not price_match:
            return None
        price = float(price_match.group(1))
        prev_close = float(prev_match.group(1)) if prev_match else None
        change = (price - prev_close) if prev_close else 0
        change_pct = (change / prev_close * 100) if prev_close else 0
        return {
            "price": round(price, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "prev_close": round(prev_close, 2) if prev_close else None,
        }
    except Exception:
        return None

# --- Yahoo Finance Direct API (no yfinance library) ---
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

def _yahoo_chart(symbol, range_str="2d", interval="1d"):
    try:
        url = f"{YAHOO_CHART_URL}/{symbol}"
        params = {"range": range_str, "interval": interval, "includePrePost": "false"}
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, params=params, headers=headers, timeout=8)
        if r.status_code != 200:
            return None
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        return result[0]
    except Exception:
        return None

def safe_float(val):
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None

# --- Mappings ---
INDIAN_INDICES = {
    "NIFTY 50": "^NSEI",
    "SENSEX": "^BSESN",
    "NIFTY BANK": "^NSEBANK",
    "NIFTY IT": "^CNXIT",
    "NIFTY MIDCAP 100": "NIFTYMIDCAP100.NS",
    "NIFTY SMALLCAP 100": "^CNXSC",
}

GOOGLE_INDEX_MAP = {
    "NIFTY 50": ("NIFTY_50", "INDEXNSE"),
    "SENSEX": ("SENSEX", "INDEXBOM"),
    "NIFTY BANK": ("NIFTY_BANK", "INDEXNSE"),
    "NIFTY IT": ("NIFTY_IT", "INDEXNSE"),
}

POPULAR_STOCKS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BAJFINANCE", "BHARTIARTL",
    "WIPRO", "AXISBANK", "MARUTI", "TITAN", "SUNPHARMA",
]
# --- Helpers ---
def _fetch_index_yahoo(name, symbol):
    chart = _yahoo_chart(symbol, "2d", "1d")
    if not chart:
        return None
    meta = chart.get("meta", {})
    closes = chart.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    highs = chart.get("indicators", {}).get("quote", [{}])[0].get("high", [])
    lows = chart.get("indicators", {}).get("quote", [{}])[0].get("low", [])
    if not closes or len(closes) < 1:
        return None
    price = closes[-1]
    prev = closes[-2] if len(closes) > 1 else meta.get("chartPreviousClose", price)
    if price is None:
        return None
    change = price - prev if prev else 0
    change_pct = (change / prev * 100) if prev else 0
    return {
        "name": name, "symbol": symbol,
        "price": safe_float(price), "change": safe_float(change),
        "change_pct": safe_float(change_pct),
        "high": safe_float(highs[-1] if highs else None),
        "low": safe_float(lows[-1] if lows else None),
    }

def _fetch_index_google(name):
    mapping = GOOGLE_INDEX_MAP.get(name)
    if not mapping:
        return None
    symbol, exchange = mapping
    data = _google_finance_quote(symbol, exchange)
    if not data:
        return None
    return {
        "name": name, "symbol": INDIAN_INDICES.get(name, symbol),
        "price": data["price"], "change": data["change"],
        "change_pct": data["change_pct"], "high": None, "low": None,
    }

def _fetch_stock_quote(symbol_clean):
    data = _google_finance_quote(symbol_clean, "NSE")
    if data:
        return {
            "symbol": f"{symbol_clean}.NS", "price": data["price"],
            "change": data["change"], "change_pct": data["change_pct"],
            "open": None, "high": None, "low": None, "volume": None,
            "market_cap": None, "currency": "INR",
        }
    chart = _yahoo_chart(f"{symbol_clean}.NS", "2d", "1d")
    if not chart:
        return None
    meta = chart.get("meta", {})
    q = chart.get("indicators", {}).get("quote", [{}])[0]
    closes = q.get("close", [])
    if not closes or closes[-1] is None:
        return None
    price = closes[-1]
    prev = closes[-2] if len(closes) > 1 else meta.get("chartPreviousClose", price)
    change = price - prev if prev else 0
    change_pct = (change / prev * 100) if prev else 0
    return {
        "symbol": f"{symbol_clean}.NS", "price": safe_float(price),
        "open": safe_float(q.get("open", [None])[-1]),
        "high": safe_float(q.get("high", [None])[-1]),
        "low": safe_float(q.get("low", [None])[-1]),
        "volume": safe_float(q.get("volume", [None])[-1]),
        "change": safe_float(change), "change_pct": safe_float(change_pct),
        "market_cap": None, "currency": meta.get("currency", "INR"),
    }


# === ENDPOINTS ===

@router.get("/indices")
def get_indices():
    cached = _get_cached("indices")
    if cached is not None:
        return cached
    results = []
    # Try NSE India API first
    nse_data = _nse_fetch("/api/allIndices")
    if nse_data and "data" in nse_data:
        target = {"NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY MIDCAP 100", "NIFTY SMALLCAP 100"}
        for idx in nse_data["data"]:
            name = idx.get("index", "")
            if name in target:
                results.append({
                    "name": name, "symbol": INDIAN_INDICES.get(name, name),
                    "price": safe_float(idx.get("last")),
                    "change": safe_float(idx.get("variation")),
                    "change_pct": safe_float(idx.get("percentChange")),
                    "high": safe_float(idx.get("high")),
                    "low": safe_float(idx.get("low")),
                })
        sensex = _fetch_index_google("SENSEX") or _fetch_index_yahoo("SENSEX", "^BSESN")
        if sensex:
            results.append(sensex)
    # Fallback: Google Finance + Yahoo in parallel
    if len(results) < 3:
        results = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {}
            for name, symbol in INDIAN_INDICES.items():
                futures[executor.submit(_fetch_index_google, name)] = (name, symbol)
            done_names = set()
            for future in as_completed(futures, timeout=12):
                name, symbol = futures[future]
                try:
                    data = future.result(timeout=8)
                    if data:
                        results.append(data)
                        done_names.add(name)
                except Exception:
                    continue
            missing = {n: s for n, s in INDIAN_INDICES.items() if n not in done_names}
            if missing:
                yf = {executor.submit(_fetch_index_yahoo, n, s): n for n, s in missing.items()}
                for future in as_completed(yf, timeout=12):
                    try:
                        data = future.result(timeout=8)
                        if data:
                            results.append(data)
                    except Exception:
                        continue
    if results:
        _set_cached("indices", results)
    return results


@router.get("/search")
def search_stocks(q: str = Query(..., description="Search query")):
    query = q.strip().upper()
    candidates = []
    data = _google_finance_quote(query, "NSE")
    if data:
        candidates.append({"symbol": f"{query}.NS", "name": query, "exchange": "NSE", "price": data["price"], "currency": "INR"})
    for sym in POPULAR_STOCKS:
        if query in sym and sym != query:
            quote = _google_finance_quote(sym, "NSE")
            if quote:
                candidates.append({"symbol": f"{sym}.NS", "name": sym, "exchange": "NSE", "price": quote["price"], "currency": "INR"})
    return candidates[:10]


@router.get("/quote")
def get_quotes(symbols: str = Query(..., description="Comma-separated symbols")):
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch_stock_quote, s.replace(".NS","").replace(".BO","")): s for s in syms}
        for future in as_completed(futures, timeout=15):
            try:
                data = future.result(timeout=10)
                if data:
                    results.append(data)
            except Exception:
                continue
    return results


@router.get("/historical/{symbol}")
def get_historical(symbol: str, period: str = Query("1y"), interval: str = Query("1d")):
    try:
        chart = _yahoo_chart(symbol, period, interval)
        if not chart:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")
        timestamps = chart.get("timestamp", [])
        q = chart.get("indicators", {}).get("quote", [{}])[0]
        records = []
        for i, ts in enumerate(timestamps):
            records.append({
                "date": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d"),
                "open": safe_float(q.get("open", [])[i] if i < len(q.get("open", [])) else None),
                "high": safe_float(q.get("high", [])[i] if i < len(q.get("high", [])) else None),
                "low": safe_float(q.get("low", [])[i] if i < len(q.get("low", [])) else None),
                "close": safe_float(q.get("close", [])[i] if i < len(q.get("close", [])) else None),
                "volume": safe_float(q.get("volume", [])[i] if i < len(q.get("volume", [])) else None),
            })
        return {"symbol": symbol, "period": period, "interval": interval, "data": records}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/earnings/{symbol}")
def get_earnings(symbol: str):
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        quarterly_income = t.quarterly_income_stmt
        eps_data = t.quarterly_earnings
        result = {"symbol": symbol, "quarterly": []}
        if quarterly_income is not None and not quarterly_income.empty:
            df = quarterly_income.T
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            for date, row in df.iterrows():
                result["quarterly"].append({
                    "quarter": date.strftime("%b %Y"), "date": date.strftime("%Y-%m-%d"),
                    "revenue": safe_float(row.get("Total Revenue")),
                    "gross_profit": safe_float(row.get("Gross Profit")),
                    "operating_income": safe_float(row.get("Operating Income")),
                    "net_income": safe_float(row.get("Net Income")),
                    "ebitda": safe_float(row.get("EBITDA")),
                })
        if eps_data is not None and not eps_data.empty:
            eps_data = eps_data.reset_index()
            for _, row in eps_data.iterrows():
                q_str = str(row.get("Date", ""))
                for entry in result["quarterly"]:
                    if q_str[:7] == entry["date"][:7]:
                        entry["eps"] = safe_float(row.get("Earnings"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/earnings-batch")
def get_earnings_batch(symbols: str = Query(...)):
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    results = []
    for sym in syms:
        try:
            results.append(get_earnings(sym))
        except Exception:
            results.append({"symbol": sym, "quarterly": [], "error": "Data unavailable"})
    return results


@router.get("/movers")
def get_top_movers():
    cached = _get_cached("movers")
    if cached is not None:
        return cached
    results = []
    # Try NSE API for NIFTY 50 constituents
    nse_data = _nse_fetch("/api/equity-stockIndices?index=NIFTY%2050")
    if nse_data and "data" in nse_data:
        for stock in nse_data["data"]:
            sym = stock.get("symbol", "")
            if sym == "NIFTY 50":
                continue
            pct = stock.get("pChange")
            if pct is not None:
                results.append({
                    "symbol": f"{sym}.NS", "price": safe_float(stock.get("lastPrice")),
                    "open": safe_float(stock.get("open")),
                    "high": safe_float(stock.get("dayHigh")),
                    "low": safe_float(stock.get("dayLow")),
                    "volume": None, "change": safe_float(stock.get("change")),
                    "change_pct": safe_float(pct), "market_cap": None, "currency": "INR",
                })
    # Fallback: Google Finance for top stocks (reduced set for speed)
    if len(results) < 5:
        results = []
        top_stocks = POPULAR_STOCKS[:8]
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_fetch_stock_quote, sym): sym for sym in top_stocks}
            for future in as_completed(futures, timeout=10):
                try:
                    data = future.result(timeout=6)
                    if data:
                        results.append(data)
                except Exception:
                    continue
    gainers = sorted([r for r in results if (r.get("change_pct") or 0) > 0],
                     key=lambda x: x.get("change_pct", 0), reverse=True)[:5]
    losers = sorted([r for r in results if (r.get("change_pct") or 0) < 0],
                    key=lambda x: x.get("change_pct", 0))[:5]
    result = {"gainers": gainers, "losers": losers}
    if results:
        _set_cached("movers", result)
    return result
