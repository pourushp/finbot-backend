from fastapi import APIRouter, UploadFile, File, HTTPException
import yfinance as yf
import pandas as pd
import numpy as np
from io import StringIO
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta

router = APIRouter()


def safe_float(val):
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return float(val)
    except Exception:
        return None


def forecast_price(prices: list, days_ahead: int) -> float:
    """Simple linear regression forecast."""
    if len(prices) < 5:
        return prices[-1] if prices else 0
    X = np.arange(len(prices)).reshape(-1, 1)
    y = np.array(prices)
    model = LinearRegression()
    model.fit(X, y)
    future_X = np.array([[len(prices) + days_ahead]])
    return float(model.predict(future_X)[0])


def calculate_cagr(start_value: float, end_value: float, years: float) -> float:
    """Calculate CAGR."""
    if start_value <= 0 or years <= 0:
        return 0
    return ((end_value / start_value) ** (1 / years) - 1) * 100


@router.post("/upload")
async def upload_portfolio(file: UploadFile = File(...)):
    """
    Upload portfolio CSV.
    Expected columns: Symbol, Quantity, BuyPrice, BuyDate
    Example: RELIANCE.NS,10,2400.50,2023-01-15
    """
    try:
        content = await file.read()
        text = content.decode("utf-8")
        df = pd.read_csv(StringIO(text))

        # Normalize column names
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        required = {"symbol", "quantity", "buyprice"}
        col_map = {}

        # Flexible column mapping
        for col in df.columns:
            c = col.lower().replace(" ", "_").replace("-", "_")
            if "symbol" in c or "ticker" in c or "stock" in c:
                col_map["symbol"] = col
            elif "qty" in c or "quantity" in c or "units" in c or "shares" in c:
                col_map["quantity"] = col
            elif "buy_price" in c or "buyprice" in c or "cost" in c or "avg" in c or "price" in c:
                col_map["buy_price"] = col
            elif "date" in c or "purchase" in c:
                col_map["buy_date"] = col

        if "symbol" not in col_map or "quantity" not in col_map or "buy_price" not in col_map:
            raise HTTPException(
                status_code=400,
                detail="CSV must have columns: Symbol, Quantity, BuyPrice (and optionally BuyDate)"
            )

        holdings = []
        total_invested = 0
        total_current = 0

        for _, row in df.iterrows():
            symbol = str(row[col_map["symbol"]]).strip()
            quantity = float(row[col_map["quantity"]])
            buy_price = float(row[col_map["buy_price"]])
            buy_date = row.get(col_map.get("buy_date", ""), None)
            if buy_date:
                buy_date = str(buy_date)[:10]

            # Fetch current price
            try:
                t = yf.Ticker(symbol)
                hist = t.history(period="1d")
                current_price = float(hist.iloc[-1]["Close"]) if not hist.empty else buy_price
            except Exception:
                current_price = buy_price

            invested = quantity * buy_price
            current_val = quantity * current_price
            gain_loss = current_val - invested
            gain_loss_pct = (gain_loss / invested) * 100 if invested > 0 else 0

            total_invested += invested
            total_current += current_val

            holdings.append({
                "symbol": symbol,
                "quantity": quantity,
                "buy_price": buy_price,
                "buy_date": buy_date,
                "current_price": safe_float(current_price),
                "invested": safe_float(invested),
                "current_value": safe_float(current_val),
                "gain_loss": safe_float(gain_loss),
                "gain_loss_pct": safe_float(gain_loss_pct),
                "weight": 0,  # will compute after
            })

        # Compute portfolio weights
        for h in holdings:
            h["weight"] = (h["current_value"] / total_current * 100) if total_current > 0 else 0

        total_gain_loss = total_current - total_invested
        total_gain_loss_pct = (total_gain_loss / total_invested * 100) if total_invested > 0 else 0

        return {
            "holdings": holdings,
            "summary": {
                "total_invested": safe_float(total_invested),
                "total_current_value": safe_float(total_current),
                "total_gain_loss": safe_float(total_gain_loss),
                "total_gain_loss_pct": safe_float(total_gain_loss_pct),
                "num_holdings": len(holdings),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.get("/historical-performance")
def portfolio_historical(
    symbols: str,
    quantities: str,
    buy_prices: str,
    period: str = "1y",
):
    """
    Generate historical portfolio value over time.
    symbols, quantities, buy_prices are comma-separated parallel lists.
    """
    try:
        syms = [s.strip() for s in symbols.split(",")]
        qtys = [float(q.strip()) for q in quantities.split(",")]
        buys = [float(b.strip()) for b in buy_prices.split(",")]

        if not (len(syms) == len(qtys) == len(buys)):
            raise HTTPException(status_code=400, detail="Lists must be same length")

        # Get historical close for each
        all_data = {}
        for sym in syms:
            try:
                t = yf.Ticker(sym)
                hist = t.history(period=period)
                hist = hist.reset_index()
                for _, row in hist.iterrows():
                    date_str = row["Date"].strftime("%Y-%m-%d")
                    if date_str not in all_data:
                        all_data[date_str] = 0
                    idx = syms.index(sym)
                    all_data[date_str] += qtys[idx] * float(row["Close"])
            except Exception:
                continue

        timeline = [{"date": d, "value": v} for d, v in sorted(all_data.items())]

        # Baseline (invested amount)
        total_invested = sum(q * b for q, b in zip(qtys, buys))

        return {
            "timeline": timeline,
            "total_invested": total_invested,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forecast/{symbol}")
def forecast_stock(symbol: str):
    """Generate short/medium/long-term price forecasts using linear regression on 2yr data."""
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="2y")
        if hist.empty:
            raise HTTPException(status_code=404, detail="No data")

        closes = list(hist["Close"].values)

        # Last known price
        current = closes[-1]

        short_days = 7     # 1 week
        medium_days = 30   # 1 month
        long_days = 180    # 6 months

        # Use last 90 days for short, 180 for medium, all for long
        short_forecast = forecast_price(closes[-90:], short_days)
        medium_forecast = forecast_price(closes[-180:], medium_days)
        long_forecast = forecast_price(closes, long_days)

        # 52-week high/low
        recent = closes[-252:] if len(closes) >= 252 else closes
        high_52w = max(recent)
        low_52w = min(recent)

        # Simple MA signals
        ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else current
        ma50 = np.mean(closes[-50:]) if len(closes) >= 50 else current
        ma200 = np.mean(closes[-200:]) if len(closes) >= 200 else current

        def signal(forecast_val):
            pct = (forecast_val - current) / current * 100
            if pct > 5:
                return "Bullish"
            elif pct < -5:
                return "Bearish"
            else:
                return "Neutral"

        return {
            "symbol": symbol,
            "current_price": safe_float(current),
            "high_52w": safe_float(high_52w),
            "low_52w": safe_float(low_52w),
            "ma20": safe_float(ma20),
            "ma50": safe_float(ma50),
            "ma200": safe_float(ma200),
            "ma_signal": "Bullish" if ma50 > ma200 else "Bearish",
            "forecasts": {
                "short_term": {
                    "label": "1 Week",
                    "price": safe_float(short_forecast),
                    "change_pct": safe_float((short_forecast - current) / current * 100),
                    "signal": signal(short_forecast),
                },
                "medium_term": {
                    "label": "1 Month",
                    "price": safe_float(medium_forecast),
                    "change_pct": safe_float((medium_forecast - current) / current * 100),
                    "signal": signal(medium_forecast),
                },
                "long_term": {
                    "label": "6 Months",
                    "price": safe_float(long_forecast),
                    "change_pct": safe_float((long_forecast - current) / current * 100),
                    "signal": signal(long_forecast),
                },
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
