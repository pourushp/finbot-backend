from fastapi import APIRouter, Query, HTTPException
import httpx
import asyncio

router = APIRouter()

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

POPULAR_COINS = [
    "bitcoin", "ethereum", "binancecoin", "solana", "ripple",
    "cardano", "avalanche-2", "polkadot", "chainlink", "matic-network",
    "dogecoin", "shiba-inu", "tron", "litecoin", "uniswap",
]


async def cg_get(path: str, params: dict = None):
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{COINGECKO_BASE}{path}", params=params or {})
        resp.raise_for_status()
        return resp.json()


@router.get("/markets")
async def get_crypto_markets(
    vs_currency: str = Query("inr", description="Currency: inr, usd"),
    per_page: int = Query(20, ge=1, le=50),
):
    """Get top cryptocurrencies by market cap in INR or USD."""
    try:
        data = await cg_get("/coins/markets", {
            "vs_currency": vs_currency,
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": 1,
            "sparkline": False,
            "price_change_percentage": "24h,7d",
        })
        return [
            {
                "id": c["id"],
                "symbol": c["symbol"].upper(),
                "name": c["name"],
                "image": c["image"],
                "price": c["current_price"],
                "market_cap": c["market_cap"],
                "market_cap_rank": c["market_cap_rank"],
                "change_24h": c.get("price_change_percentage_24h"),
                "change_7d": c.get("price_change_percentage_7d_in_currency"),
                "volume_24h": c["total_volume"],
                "high_24h": c["high_24h"],
                "low_24h": c["low_24h"],
                "currency": vs_currency.upper(),
            }
            for c in data
        ]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="CoinGecko API error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/historical/{coin_id}")
async def get_crypto_historical(
    coin_id: str,
    days: int = Query(30, description="Number of days: 1, 7, 14, 30, 90, 180, 365"),
    vs_currency: str = Query("inr"),
):
    """Get historical price data for a coin."""
    try:
        data = await cg_get(f"/coins/{coin_id}/market_chart", {
            "vs_currency": vs_currency,
            "days": days,
            "interval": "daily" if days > 7 else "hourly",
        })
        prices = [
            {"date": str(p[0])[:10] if days > 1 else p[0], "price": p[1]}
            for p in data.get("prices", [])
        ]
        return {"coin_id": coin_id, "currency": vs_currency.upper(), "days": days, "data": prices}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="CoinGecko API error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coin/{coin_id}")
async def get_coin_detail(coin_id: str):
    """Get detailed info for a single coin."""
    try:
        data = await cg_get(f"/coins/{coin_id}", {
            "localization": False,
            "tickers": False,
            "market_data": True,
            "community_data": False,
            "developer_data": False,
        })
        md = data.get("market_data", {})
        return {
            "id": data["id"],
            "symbol": data["symbol"].upper(),
            "name": data["name"],
            "description": data.get("description", {}).get("en", "")[:300],
            "price_inr": md.get("current_price", {}).get("inr"),
            "price_usd": md.get("current_price", {}).get("usd"),
            "market_cap_inr": md.get("market_cap", {}).get("inr"),
            "ath_inr": md.get("ath", {}).get("inr"),
            "atl_inr": md.get("atl", {}).get("inr"),
            "change_24h": md.get("price_change_percentage_24h"),
            "change_7d": md.get("price_change_percentage_7d"),
            "change_30d": md.get("price_change_percentage_30d"),
            "circulating_supply": md.get("circulating_supply"),
            "total_supply": md.get("total_supply"),
        }
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="CoinGecko API error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
