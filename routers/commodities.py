from fastapi import APIRouter, HTTPException
import yfinance as yf
import numpy as np

router = APIRouter()

# Commodity symbols via Yahoo Finance
COMMODITIES = {
    "Gold": {"symbol": "GC=F", "unit": "USD/oz", "mcx_symbol": "GOLD.MCX"},
    "Silver": {"symbol": "SI=F", "unit": "USD/oz", "mcx_symbol": "SILVER.MCX"},
    "Crude Oil (WTI)": {"symbol": "CL=F", "unit": "USD/bbl"},
    "Natural Gas": {"symbol": "NG=F", "unit": "USD/MMBtu"},
    "Copper": {"symbol": "HG=F", "unit": "USD/lb"},
    "Aluminium": {"symbol": "ALI=F", "unit": "USD/lb"},
    "Platinum": {"symbol": "PL=F", "unit": "USD/oz"},
    "Palladium": {"symbol": "PA=F", "unit": "USD/oz"},
    "Wheat": {"symbol": "ZW=F", "unit": "USD/bu"},
    "Cotton": {"symbol": "CT=F", "unit": "USD/lb"},
}


def safe_float(val):
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return float(val)
    except Exception:
        return None


@router.get("/")
def get_all_commodities():
    """Get current prices for all tracked commodities."""
    results = []
    for name, info in COMMODITIES.items():
        try:
            t = yf.Ticker(info["symbol"])
            hist = t.history(period="2d")
            if hist.empty:
                continue
            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else hist.iloc[-1]
            change = latest["Close"] - prev["Close"]
            change_pct = (change / prev["Close"]) * 100 if prev["Close"] else 0
            results.append({
                "name": name,
                "symbol": info["symbol"],
                "unit": info["unit"],
                "price": safe_float(latest["Close"]),
                "open": safe_float(latest["Open"]),
                "high": safe_float(latest["High"]),
                "low": safe_float(latest["Low"]),
                "change": safe_float(change),
                "change_pct": safe_float(change_pct),
            })
        except Exception:
            continue
    return results


@router.get("/historical/{symbol}")
def get_commodity_historical(symbol: str, period: str = "1y", interval: str = "1d"):
    """Get historical data for a commodity."""
    try:
        # Map friendly name to symbol if needed
        friendly = {v["symbol"]: v for v in COMMODITIES.values()}
        t = yf.Ticker(symbol)
        hist = t.history(period=period, interval=interval)
        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")
        hist = hist.reset_index()
        records = []
        for _, row in hist.iterrows():
            date_val = row["Date"]
            records.append({
                "date": date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)[:10],
                "open": safe_float(row["Open"]),
                "high": safe_float(row["High"]),
                "low": safe_float(row["Low"]),
                "close": safe_float(row["Close"]),
            })
        return {"symbol": symbol, "period": period, "data": records}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
