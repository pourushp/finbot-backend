from fastapi import APIRouter, Query, HTTPException
import httpx
import pandas as pd
from io import StringIO

router = APIRouter()

MFAPI_BASE = "https://api.mfapi.in"
AMFI_NAV_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

# Cached fund list
_fund_cache = None


async def fetch_amfi_funds() -> list:
    """Fetch and parse all AMFI fund data."""
    global _fund_cache
    if _fund_cache is not None:
        return _fund_cache
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(AMFI_NAV_URL)
            resp.raise_for_status()
            text = resp.text

        funds = []
        current_amc = ""
        current_category = ""
        lines = text.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("Scheme Code"):
                continue
            # AMC header line (no semicolons)
            if ";" not in line:
                if line and not line.startswith("Open"):
                    current_amc = line
                    if "Equity" in line:
                        current_category = "Equity"
                    elif "Debt" in line or "Liquid" in line or "Money Market" in line:
                        current_category = "Debt"
                    elif "Hybrid" in line or "Balanced" in line:
                        current_category = "Hybrid"
                    elif "Index" in line or "ETF" in line:
                        current_category = "Index/ETF"
                    elif "ELSS" in line or "Tax" in line:
                        current_category = "ELSS"
                    else:
                        current_category = "Other"
                continue

            parts = line.split(";")
            if len(parts) < 6:
                continue

            scheme_code = parts[0].strip()
            isin_growth = parts[1].strip()
            scheme_name = parts[3].strip()
            nav_str = parts[4].strip()
            nav_date = parts[7].strip() if len(parts) > 7 else ""

            try:
                nav = float(nav_str)
            except ValueError:
                nav = None

            if scheme_code and scheme_name and nav:
                funds.append({
                    "scheme_code": scheme_code,
                    "isin": isin_growth,
                    "name": scheme_name,
                    "amc": current_amc,
                    "category": current_category,
                    "nav": nav,
                    "nav_date": nav_date,
                })

        _fund_cache = funds
        return funds
    except Exception as e:
        return []


@router.get("/search")
async def search_funds(q: str = Query(..., description="Fund name or AMC to search")):
    """Search Indian mutual funds by name or AMC."""
    try:
        funds = await fetch_amfi_funds()
        if not funds:
            # Fallback: use mfapi search
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{MFAPI_BASE}/mf/search", params={"q": q})
                if resp.status_code == 200:
                    data = resp.json()
                    return [{"scheme_code": str(f.get("schemeCode", "")), "name": f.get("schemeName", ""), "amc": "", "category": "", "nav": None} for f in data[:20]]
            return []

        query = q.lower()
        matches = [
            f for f in funds
            if query in f["name"].lower() or query in f["amc"].lower()
        ]
        return matches[:20]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/nav/{scheme_code}")
async def get_fund_nav_history(
    scheme_code: str,
    days: int = Query(365, description="Number of days of NAV history"),
):
    """Get historical NAV data for a mutual fund."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{MFAPI_BASE}/mf/{scheme_code}")
            resp.raise_for_status()
            data = resp.json()

        nav_data = data.get("data", [])
        meta = data.get("meta", {})

        # nav_data is list of {"date": "DD-MM-YYYY", "nav": "value"}
        records = []
        for entry in nav_data[:days]:
            try:
                date_parts = entry["date"].split("-")
                iso_date = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]}"
                records.append({
                    "date": iso_date,
                    "nav": float(entry["nav"]),
                })
            except Exception:
                continue

        records.sort(key=lambda x: x["date"])

        # Calculate returns
        if len(records) >= 2:
            current_nav = records[-1]["nav"]
            returns = {}
            checkpoints = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365, "3Y": 1095, "5Y": 1825}
            for label, d in checkpoints.items():
                if len(records) >= d:
                    past_nav = records[-d]["nav"]
                    ret = ((current_nav - past_nav) / past_nav) * 100
                    returns[label] = round(ret, 2)
                else:
                    returns[label] = None
        else:
            returns = {}

        return {
            "scheme_code": scheme_code,
            "name": meta.get("scheme_name", ""),
            "amc": meta.get("fund_house", ""),
            "category": meta.get("scheme_category", ""),
            "type": meta.get("scheme_type", ""),
            "current_nav": records[-1]["nav"] if records else None,
            "returns": returns,
            "history": records,
        }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=404, detail=f"Fund {scheme_code} not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def get_fund_categories():
    """Get list of all fund categories available."""
    return [
        {"id": "equity_large", "label": "Large Cap Equity", "risk": "High", "horizon": "5+ years"},
        {"id": "equity_mid", "label": "Mid Cap Equity", "risk": "Very High", "horizon": "7+ years"},
        {"id": "equity_small", "label": "Small Cap Equity", "risk": "Very High", "horizon": "7+ years"},
        {"id": "elss", "label": "ELSS (Tax Saving)", "risk": "High", "horizon": "3+ years (lock-in)"},
        {"id": "hybrid_balanced", "label": "Hybrid Balanced", "risk": "Medium", "horizon": "3-5 years"},
        {"id": "debt_liquid", "label": "Liquid / Money Market", "risk": "Low", "horizon": "< 1 year"},
        {"id": "debt_short", "label": "Short Duration Debt", "risk": "Low-Medium", "horizon": "1-3 years"},
        {"id": "index_nifty", "label": "Index (NIFTY 50)", "risk": "High", "horizon": "5+ years"},
        {"id": "index_sensex", "label": "Index (SENSEX)", "risk": "High", "horizon": "5+ years"},
        {"id": "international", "label": "International / Global", "risk": "High", "horizon": "5+ years"},
    ]


@router.get("/recommendations")
async def get_recommendations(
    risk: str = Query("medium", description="low, medium, high"),
    horizon: str = Query("medium", description="short (< 1yr), medium (1-5yr), long (5yr+)"),
    goal: str = Query("growth", description="growth, income, tax-saving, safety"),
):
    """Get fund type recommendations based on risk profile."""
    recommendations = []

    if goal == "tax-saving":
        recommendations.append({
            "category": "ELSS (Tax Saving)",
            "rationale": "Save up to ₹1.5L under 80C with 3-year lock-in",
            "suggested_funds": ["Mirae Asset Tax Saver Fund", "Axis Long Term Equity Fund", "Parag Parikh ELSS Tax Saver"],
            "risk_level": "High",
            "min_horizon": "3 years",
        })

    if risk == "low" or goal == "safety":
        recommendations.append({
            "category": "Liquid / Money Market Funds",
            "rationale": "Capital preservation with better returns than savings accounts",
            "suggested_funds": ["HDFC Liquid Fund", "SBI Liquid Fund", "Nippon India Liquid Fund"],
            "risk_level": "Low",
            "min_horizon": "1 week to 1 year",
        })
        if horizon in ["medium", "long"]:
            recommendations.append({
                "category": "Short Duration Debt Funds",
                "rationale": "Stable returns, low volatility for 1-3 year horizon",
                "suggested_funds": ["HDFC Short Term Debt Fund", "Kotak Bond Short Term Fund"],
                "risk_level": "Low-Medium",
                "min_horizon": "1-3 years",
            })

    if risk == "medium":
        recommendations.append({
            "category": "Hybrid Balanced Advantage Funds",
            "rationale": "Mix of equity and debt; dynamically managed allocation",
            "suggested_funds": ["HDFC Balanced Advantage Fund", "ICICI Pru Balanced Advantage Fund", "Nippon India Balanced Advantage Fund"],
            "risk_level": "Medium",
            "min_horizon": "3+ years",
        })
        if horizon in ["medium", "long"]:
            recommendations.append({
                "category": "Large Cap Equity Funds / Index Funds",
                "rationale": "Stable equity returns with diversification across top 100 companies",
                "suggested_funds": ["Mirae Asset Large Cap Fund", "UTI Nifty 50 Index Fund", "HDFC Index Fund Nifty 50"],
                "risk_level": "High",
                "min_horizon": "5+ years",
            })

    if risk == "high":
        if horizon == "long":
            recommendations.append({
                "category": "Mid & Small Cap Equity",
                "rationale": "Higher return potential over 7+ year horizon",
                "suggested_funds": ["Axis Midcap Fund", "Kotak Emerging Equity Fund", "SBI Small Cap Fund"],
                "risk_level": "Very High",
                "min_horizon": "7+ years",
            })
        recommendations.append({
            "category": "Flexi Cap / Multi Cap Funds",
            "rationale": "Flexible allocation across market caps for optimal returns",
            "suggested_funds": ["Parag Parikh Flexi Cap Fund", "PGIM India Flexi Cap Fund", "UTI Flexi Cap Fund"],
            "risk_level": "High",
            "min_horizon": "5+ years",
        })

    return {
        "risk_profile": risk,
        "investment_horizon": horizon,
        "goal": goal,
        "recommendations": recommendations,
    }
