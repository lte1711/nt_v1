from __future__ import annotations

from fastapi import APIRouter

from .investor_service import (
    get_investor_positions_service,
    get_investor_open_orders_service,
    post_investor_order_service,
    get_investor_account_service,
)


router = APIRouter(tags=["investor"])


@router.get("/api/v1/investor/positions")
async def get_investor_positions() -> dict:
    return await get_investor_positions_service()


@router.get("/api/v1/ops/positions")
async def get_ops_positions_alias() -> dict:
    return await get_investor_positions_service()


@router.get("/api/v1/trading/open-orders")
async def get_trading_open_orders(limit: int = 200) -> dict:
    return await get_investor_open_orders_service(limit=limit)


@router.get("/api/investor/account")
async def get_investor_account() -> dict:
    return await get_investor_account_service()


@router.post("/api/investor/order")
async def post_investor_order(payload: dict) -> dict:
    return await post_investor_order_service(payload)
