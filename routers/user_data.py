"""User data endpoints — watchlists, portfolio, alerts.
Requires Supabase. If SUPABASE_URL is not set, returns 503."""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
import os
import httpx

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")


def _supabase_headers(authorization: str):
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": authorization,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _check_configured():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")


# === WATCHLIST ===

@router.get("/watchlist")
async def get_watchlist(authorization: str = Header(...)):
    _check_configured()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/watchlists?select=*&order=added_at.asc",
            headers=_supabase_headers(authorization),
        )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.post("/watchlist")
async def add_to_watchlist(body: dict, authorization: str = Header(...)):
    _check_configured()
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/watchlists",
            json={"symbol": body["symbol"], "user_id": body.get("user_id")},
            headers=_supabase_headers(authorization),
        )
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.delete("/watchlist/{symbol}")
async def remove_from_watchlist(symbol: str, authorization: str = Header(...)):
    _check_configured()
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{SUPABASE_URL}/rest/v1/watchlists?symbol=eq.{symbol}",
            headers=_supabase_headers(authorization),
        )
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return {"status": "deleted"}


# === PORTFOLIO ===

@router.get("/portfolio/holdings")
async def get_holdings(authorization: str = Header(...)):
    _check_configured()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/portfolio_holdings?select=*&order=created_at.asc",
            headers=_supabase_headers(authorization),
        )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.post("/portfolio/holdings")
async def add_holding(body: dict, authorization: str = Header(...)):
    _check_configured()
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/portfolio_holdings",
            json=body,
            headers=_supabase_headers(authorization),
        )
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.delete("/portfolio/holdings/{holding_id}")
async def remove_holding(holding_id: str, authorization: str = Header(...)):
    _check_configured()
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{SUPABASE_URL}/rest/v1/portfolio_holdings?id=eq.{holding_id}",
            headers=_supabase_headers(authorization),
        )
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return {"status": "deleted"}


# === PRICE ALERTS ===

@router.get("/alerts")
async def get_alerts(authorization: str = Header(...)):
    _check_configured()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{SUPABASE_URL}/rest/v1/price_alerts?select=*&order=created_at.desc",
            headers=_supabase_headers(authorization),
        )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.post("/alerts")
async def create_alert(body: dict, authorization: str = Header(...)):
    _check_configured()
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{SUPABASE_URL}/rest/v1/price_alerts",
            json=body,
            headers=_supabase_headers(authorization),
        )
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, authorization: str = Header(...)):
    _check_configured()
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{SUPABASE_URL}/rest/v1/price_alerts?id=eq.{alert_id}",
            headers=_supabase_headers(authorization),
        )
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return {"status": "deleted"}


@router.patch("/alerts/{alert_id}")
async def toggle_alert(alert_id: str, body: dict, authorization: str = Header(...)):
    _check_configured()
    async with httpx.AsyncClient() as client:
        r = await client.patch(
            f"{SUPABASE_URL}/rest/v1/price_alerts?id=eq.{alert_id}",
            json=body,
            headers=_supabase_headers(authorization),
        )
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json() if r.status_code == 200 else {"status": "updated"}
