from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import HTTPException
import requests

DEFAULT_FUTURES_TESTNET_BASE = "https://demo-fapi.binance.com"
_SYMBOL_FILTER_CACHE: dict[str, dict[str, float]] = {}
_SYMBOL_FILTER_CACHE_TS: dict[str, float] = {}
_SYMBOL_FILTER_CACHE_TTL_SEC = 300.0
_REJECT_COOLDOWN_CACHE: dict[str, float] = {}
_REJECT_COOLDOWN_TTL_SEC = 45.0
_POSITIONS_CACHE: dict[str, Any] = {"expires_at": 0.0, "value": None}
_POSITIONS_CACHE_TTL_SEC = 10.0


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_runtime_env_defaults() -> None:
    env_path = _project_root() / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and not os.getenv(key):
                os.environ[key] = value
    except Exception:
        return

    api_key = os.getenv("BINANCE_TESTNET_API_KEY", "").strip()
    api_secret = (
        os.getenv("BINANCE_TESTNET_API_SECRET", "").strip()
        or os.getenv("BINANCE_TESTNET_SECRET", "").strip()
    )
    if api_key and not os.getenv("BINANCE_TESTNET_KEY_PLACEHOLDER"):
        os.environ["BINANCE_TESTNET_KEY_PLACEHOLDER"] = api_key
    if api_secret and not os.getenv("BINANCE_TESTNET_SECRET_PLACEHOLDER"):
        os.environ["BINANCE_TESTNET_SECRET_PLACEHOLDER"] = api_secret


def _runtime_event_path() -> Path:
    return _project_root() / "logs" / "runtime" / "investor_order_api.jsonl"


def _resolve_api_base() -> str:
    base = (
        os.getenv("BINANCE_FUTURES_TESTNET_BASE_URL")
        or os.getenv("BINANCE_TESTNET_BASE_URL")
        or DEFAULT_FUTURES_TESTNET_BASE
    ).strip()
    if not base:
        base = DEFAULT_FUTURES_TESTNET_BASE
    return base.rstrip("/")


def _fetch_mark_price(symbol: str) -> float:
    try:
        with urlopen(
            f"https://demo-fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}",
            timeout=5,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        exchange_code, exchange_msg = _parse_exchange_error(body)
        raise HTTPException(
            status_code=422,
            detail={
                "submit_called": False,
                "status": 422,
                "exchange_code": exchange_code,
                "exchange_msg": exchange_msg or f"unsupported symbol: {symbol}",
                "symbol": symbol,
                "order_terminal": True,
                "entry_filled_qty": 0.0,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "submit_called": False,
                "status": 422,
                "exchange_code": None,
                "exchange_msg": f"mark price lookup failed for symbol={symbol}: {exc}",
                "symbol": symbol,
                "order_terminal": True,
                "entry_filled_qty": 0.0,
            },
        ) from exc

    if "price" not in payload:
        raise HTTPException(
            status_code=422,
            detail={
                "submit_called": False,
                "status": 422,
                "exchange_code": None,
                "exchange_msg": f"price missing for symbol={symbol}",
                "symbol": symbol,
                "order_terminal": True,
                "entry_filled_qty": 0.0,
            },
        )
    return float(payload["price"])


def _get_binance_server_time() -> int:
    response = requests.get(
        f"{DEFAULT_FUTURES_TESTNET_BASE}/fapi/v1/time",
        timeout=5,
    )
    response.raise_for_status()
    payload = response.json()
    return int(payload["serverTime"])


def _client_order_id_from_trace(trace_id: str) -> str:
    cleaned = "".join(ch for ch in str(trace_id) if ch.isalnum() or ch in "-_")
    if not cleaned:
        cleaned = f"nt{uuid.uuid4().hex[:12]}"
    return cleaned[:36]


def _normalize_order_payload(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action", "")).strip().lower()
    if action == "cancel_protection_orders":
        symbol = str(payload.get("symbol", "")).upper().strip()
        client_order_ids = [
            str(value).strip()
            for value in (payload.get("client_order_ids") or [])
            if str(value).strip()
        ]
        if not symbol:
            raise HTTPException(status_code=422, detail="symbol is required for cancel_protection_orders")
        if not client_order_ids:
            raise HTTPException(status_code=422, detail="client_order_ids are required for cancel_protection_orders")
        trace_id = str(payload.get("trace_id") or f"inv-{uuid.uuid4().hex[:12]}")
        return {
            "action": action,
            "trace_id": trace_id,
            "symbol": symbol,
            "client_order_ids": client_order_ids,
            "profile": str(payload.get("profile", "TESTNET_INTRADAY_SCALP")).strip() or "TESTNET_INTRADAY_SCALP",
            "dry_run": bool(payload.get("dry_run", False)),
        }

    symbol = str(payload.get("symbol", "")).upper().strip()
    side = str(payload.get("side", "")).upper().strip()
    order_type = str(payload.get("type", "MARKET")).upper().strip() or "MARKET"
    quantity_raw = payload.get("qty", payload.get("quantity"))
    profile = str(payload.get("profile", "TESTNET_INTRADAY_SCALP")).strip() or "TESTNET_INTRADAY_SCALP"
    reduce_only = bool(payload.get("reduceOnly", False))
    dry_run = bool(payload.get("dry_run", False))
    close_position = bool(payload.get("closePosition", False))
    stop_price_raw = payload.get("stopPrice", payload.get("stop_price"))
    working_type = str(payload.get("workingType", payload.get("working_type", "MARK_PRICE"))).upper().strip() or "MARK_PRICE"

    quantity = 0.0
    if quantity_raw not in (None, ""):
        try:
            quantity = float(quantity_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="quantity must be a positive number")

    if not symbol:
        raise HTTPException(status_code=422, detail="symbol is required")
    if side not in {"BUY", "SELL"}:
        raise HTTPException(status_code=422, detail="side must be BUY or SELL")
    if quantity <= 0 and not close_position:
        raise HTTPException(status_code=422, detail="quantity must be positive")
    if order_type not in {"MARKET", "LIMIT", "STOP_MARKET", "TAKE_PROFIT_MARKET"}:
        raise HTTPException(status_code=422, detail="type must be MARKET, LIMIT, STOP_MARKET, or TAKE_PROFIT_MARKET")
    stop_price = None
    if order_type in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
        try:
            stop_price = float(stop_price_raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="stopPrice must be a positive number")
        if stop_price <= 0:
            raise HTTPException(status_code=422, detail="stopPrice must be positive")
        if working_type not in {"MARK_PRICE", "CONTRACT_PRICE"}:
            raise HTTPException(status_code=422, detail="workingType must be MARK_PRICE or CONTRACT_PRICE")

    base_url = _resolve_api_base()
    trace_id = str(payload.get("trace_id") or f"inv-{uuid.uuid4().hex[:12]}")
    quantity_before_normalize = quantity
    if close_position:
        normalization_meta = {
            "step_size": 0.0,
            "min_qty": 0.0,
            "min_notional": 0.0,
            "estimated_price": None,
            "estimated_notional": None,
            "adjusted": False,
            "min_notional_guard_applied": False,
        }
    else:
        quantity, normalization_meta = _normalize_quantity_for_symbol(
            base_url=base_url,
            symbol=symbol,
            order_type=order_type,
            quantity=quantity,
            reduce_only=reduce_only,
        )

    return {
        "action": "submit_order",
        "trace_id": trace_id,
        "clientOrderId": _client_order_id_from_trace(trace_id),
        "symbol": symbol,
        "side": side,
        "type": order_type,
        "quantity": quantity,
        "reduceOnly": reduce_only,
        "profile": profile,
        "dry_run": dry_run,
        "price": payload.get("price"),
        "stopPrice": stop_price,
        "closePosition": close_position,
        "workingType": working_type,
        "quantity_before_normalize": quantity_before_normalize,
        "normalization_meta": normalization_meta,
    }


def _step_decimals(step_size: float) -> int:
    text = f"{step_size:.16f}".rstrip("0").rstrip(".")
    if "." not in text:
        return 0
    return len(text.split(".", 1)[1])


def _floor_to_step(value: float, step_size: float) -> float:
    if step_size <= 0:
        return value
    floored = math.floor(value / step_size) * step_size
    return round(floored, _step_decimals(step_size))


def _fetch_symbol_filters(base_url: str, symbol: str) -> tuple[float, float, float]:
    now = time.time()
    if symbol in _SYMBOL_FILTER_CACHE and now - _SYMBOL_FILTER_CACHE_TS.get(symbol, 0.0) < _SYMBOL_FILTER_CACHE_TTL_SEC:
        row = _SYMBOL_FILTER_CACHE[symbol]
        return (
            float(row.get("step_size", 0.0)),
            float(row.get("min_qty", 0.0)),
            float(row.get("min_notional", 0.0)),
        )

    step_size = 0.0
    min_qty = 0.0
    min_notional = 0.0
    url = f"{base_url}/fapi/v1/exchangeInfo"
    response = requests.get(url, timeout=8)
    response.raise_for_status()
    payload = response.json()
    for item in payload.get("symbols", []):
        if str(item.get("symbol", "")).upper() != symbol:
            continue
        market_lot = None
        lot = None
        for flt in item.get("filters", []):
            ftype = str(flt.get("filterType", "")).upper()
            if ftype == "MARKET_LOT_SIZE":
                market_lot = flt
            elif ftype == "LOT_SIZE":
                lot = flt
            elif ftype in {"MIN_NOTIONAL", "NOTIONAL"}:
                min_notional = float(flt.get("notional") or flt.get("minNotional") or 0.0)
        target = market_lot or lot or {}
        step_size = float(target.get("stepSize") or 0.0)
        min_qty = float(target.get("minQty") or 0.0)
        break

    _SYMBOL_FILTER_CACHE[symbol] = {"step_size": step_size, "min_qty": min_qty, "min_notional": min_notional}
    _SYMBOL_FILTER_CACHE_TS[symbol] = now
    return step_size, min_qty, min_notional


def _normalize_quantity_for_symbol(
    *,
    base_url: str,
    symbol: str,
    order_type: str,
    quantity: float,
    reduce_only: bool,
) -> tuple[float, dict[str, Any]]:
    try:
        step_size, min_qty, min_notional = _fetch_symbol_filters(base_url=base_url, symbol=symbol)
    except Exception:
        return quantity, {
            "step_size": 0.0,
            "min_qty": 0.0,
            "min_notional": 0.0,
            "estimated_price": None,
            "estimated_notional": None,
            "adjusted": False,
            "min_notional_guard_applied": False,
        }

    if step_size <= 0:
        return quantity, {
            "step_size": 0.0,
            "min_qty": min_qty,
            "min_notional": min_notional,
            "estimated_price": None,
            "estimated_notional": None,
            "adjusted": False,
            "min_notional_guard_applied": False,
        }

    adjusted = _floor_to_step(quantity, step_size)
    if adjusted <= 0:
        adjusted = round(step_size, _step_decimals(step_size))

    if not reduce_only and min_qty > 0 and adjusted < min_qty:
        adjusted = round(min_qty, _step_decimals(step_size))

    estimated_price = None
    estimated_notional = None
    min_notional_guard_applied = False
    if not reduce_only and min_notional > 0:
        try:
            estimated_price = _fetch_mark_price(symbol)
            estimated_notional = adjusted * estimated_price
            if estimated_notional < min_notional:
                min_qty_for_notional = math.ceil(min_notional / estimated_price / step_size) * step_size
                adjusted = round(max(adjusted, min_qty_for_notional), _step_decimals(step_size))
                estimated_notional = adjusted * estimated_price
                min_notional_guard_applied = True
        except Exception:
            estimated_price = None
            estimated_notional = None

    return adjusted, {
        "step_size": step_size,
        "min_qty": min_qty,
        "min_notional": min_notional,
        "estimated_price": estimated_price,
        "estimated_notional": estimated_notional,
        "adjusted": adjusted != quantity,
        "min_notional_guard_applied": min_notional_guard_applied,
    }


def _reject_cooldown_key(order: dict[str, Any]) -> str:
    return f"{order['symbol']}|{order['side']}|{order['quantity']}|{bool(order['reduceOnly'])}"


def _reject_cooldown_remaining(order: dict[str, Any]) -> float:
    expires_at = _REJECT_COOLDOWN_CACHE.get(_reject_cooldown_key(order), 0.0)
    return max(0.0, expires_at - time.time())


def _set_reject_cooldown(order: dict[str, Any]) -> None:
    _REJECT_COOLDOWN_CACHE[_reject_cooldown_key(order)] = time.time() + _REJECT_COOLDOWN_TTL_SEC


def _build_submit_payload(
    order: dict[str, Any],
    *,
    timestamp_ms: int,
    price_value: float,
    position_side: str,
) -> dict[str, str]:
    params = {
        "symbol": order["symbol"],
        "side": order["side"],
        "type": order["type"],
        "newClientOrderId": order["clientOrderId"],
        "timestamp": str(timestamp_ms),
        "recvWindow": "5000",
    }
    if not order.get("closePosition"):
        params["quantity"] = f"{order['quantity']}"
    if order["reduceOnly"] and not order.get("closePosition"):
        params["reduceOnly"] = "true"
        if position_side != "BOTH":
            # Hedge mode exits must declare which side is being reduced.
            params["positionSide"] = "LONG" if order["side"] == "SELL" else "SHORT"
    elif order.get("closePosition"):
        params["closePosition"] = "true"
        if position_side != "BOTH":
            params["positionSide"] = "LONG" if order["side"] == "SELL" else "SHORT"
    if order["type"] == "LIMIT":
        params["timeInForce"] = "GTC"
        params["price"] = f"{price_value}"
    elif order["type"] in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
        params["stopPrice"] = f"{float(order['stopPrice'])}"
        params["workingType"] = order.get("workingType", "MARK_PRICE")
    return params


def _signed_delete(
    *,
    base_url: str,
    api_key: str,
    api_secret: str,
    path: str,
    params: dict[str, str],
) -> dict[str, Any]:
    query_string = urlencode(params)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    url = f"{base_url}{path}?{query_string}&signature={signature}"
    response = requests.delete(
        url,
        headers={"X-MBX-APIKEY": api_key},
        timeout=10,
    )
    if response.status_code >= 400:
        exchange_code, exchange_msg = _parse_exchange_error(response.text)
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "status": response.status_code,
                "exchange_code": exchange_code,
                "exchange_msg": exchange_msg,
                "body": response.text[:300],
            },
        )
    return response.json()


def _cancel_testnet_protection_orders(order: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("BINANCE_TESTNET_KEY_PLACEHOLDER", "").strip()
    api_secret = os.getenv("BINANCE_TESTNET_SECRET_PLACEHOLDER", "").strip()
    if not api_key or not api_secret:
        raise HTTPException(status_code=400, detail="testnet credentials missing")

    base_url = _resolve_api_base()
    if order["dry_run"]:
        return {
            "ok": True,
            "dry_run": True,
            "symbol": order["symbol"],
            "trace_id": order["trace_id"],
            "cancelled_client_order_ids": list(order["client_order_ids"]),
            "results": [],
        }

    results: list[dict[str, Any]] = []
    for client_order_id in order["client_order_ids"]:
        try:
            server_time_ms = _get_binance_server_time()
            payload = _signed_delete(
                base_url=base_url,
                api_key=api_key,
                api_secret=api_secret,
                path="/fapi/v1/order",
                params={
                    "symbol": order["symbol"],
                    "origClientOrderId": client_order_id,
                    "timestamp": str(server_time_ms),
                    "recvWindow": "5000",
                },
            )
            results.append(
                {
                    "client_order_id": client_order_id,
                    "ok": True,
                    "status": payload.get("status"),
                    "exchange_order_id": payload.get("orderId"),
                }
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            results.append(
                {
                    "client_order_id": client_order_id,
                    "ok": False,
                    "status": detail.get("status"),
                    "exchange_code": detail.get("exchange_code"),
                    "exchange_msg": detail.get("exchange_msg"),
                }
            )

    return {
        "ok": True,
        "symbol": order["symbol"],
        "trace_id": order["trace_id"],
        "cancelled_client_order_ids": list(order["client_order_ids"]),
        "results": results,
    }


def _parse_exchange_error(body: str) -> tuple[int | None, str]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None, body[:300]
    code = payload.get("code")
    msg = str(payload.get("msg", body[:300]))
    return int(code) if isinstance(code, int) else None, msg


def _submit_once(
    order: dict[str, Any],
    *,
    base_url: str,
    api_key: str,
    api_secret: str,
    price_value: float,
    timestamp_ms: int,
    local_time_ms: int,
) -> dict[str, Any]:
    position_side = "BOTH"
    if order["reduceOnly"]:
        position_side = _get_position_side(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            symbol=order["symbol"],
            timestamp_ms=timestamp_ms,
        )
    params = _build_submit_payload(
        order,
        timestamp_ms=timestamp_ms,
        price_value=price_value,
        position_side=position_side,
    )
    query_string = urlencode(params)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    url = f"{base_url}/fapi/v1/order?{query_string}&signature={signature}"
    response = requests.post(
        url,
        headers={
            "X-MBX-APIKEY": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=12,
    )
    if response.status_code >= 400:
        exchange_code, exchange_msg = _parse_exchange_error(response.text)
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "submit_called": True,
                "exchange": "BINANCE_TESTNET",
                "trace_id": order["trace_id"],
                "client_order_id": order["clientOrderId"],
                "status": response.status_code,
                "body": response.text[:300],
                "symbol": order["symbol"],
                "side": order["side"],
                "quantity": order["quantity"],
                "reduceOnly": order["reduceOnly"],
                "exchange_code": exchange_code,
                "exchange_msg": exchange_msg,
                "server_time": timestamp_ms,
                "local_time": local_time_ms,
                "timestamp_used": timestamp_ms,
            },
        )
    exchange_payload = response.json()
    entry_request_qty = float(order["quantity"])
    entry_filled_qty = float(exchange_payload.get("executedQty") or 0.0)
    status = str(exchange_payload.get("status") or "").upper()
    partial_fill_detected = 0.0 < entry_filled_qty < entry_request_qty
    has_open_remainder = partial_fill_detected and status in {"NEW", "PARTIALLY_FILLED"}
    order_terminal = status in {"FILLED", "CANCELED", "EXPIRED", "REJECTED"}
    return {
        "ok": True,
        "submit_called": True,
        "exchange": "BINANCE_TESTNET",
        "trace_id": order["trace_id"],
        "client_order_id": exchange_payload.get("clientOrderId") or order["clientOrderId"],
        "exchange_order_id": exchange_payload.get("orderId"),
        "status": exchange_payload.get("status"),
        "entry_request_qty": entry_request_qty,
        "entry_filled_qty": entry_filled_qty,
        "symbol": order["symbol"],
        "side": order["side"],
        "quantity": order["quantity"],
        "reduceOnly": order["reduceOnly"],
        "profile": order["profile"],
        "price": price_value,
        "raw": exchange_payload,
        "exchange_code": exchange_payload.get("code"),
        "exchange_msg": exchange_payload.get("msg"),
        "server_time": timestamp_ms,
        "local_time": local_time_ms,
        "timestamp_used": timestamp_ms,
        "retry_on_1021": False,
        "partial_fill_detected": partial_fill_detected,
        "has_open_remainder": has_open_remainder,
        "order_terminal": order_terminal,
    }


def _signed_get(
    *,
    base_url: str,
    api_key: str,
    api_secret: str,
    path: str,
    params: dict[str, str],
) -> dict[str, Any]:
    query_string = urlencode(params)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    url = f"{base_url}{path}?{query_string}&signature={signature}"
    response = requests.get(
        url,
        headers={"X-MBX-APIKEY": api_key},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def _get_position_side(
    *,
    base_url: str,
    api_key: str,
    api_secret: str,
    symbol: str,
    timestamp_ms: int,
) -> str:
    payload = _signed_get(
        base_url=base_url,
        api_key=api_key,
        api_secret=api_secret,
        path="/fapi/v2/positionRisk",
        params={"timestamp": str(timestamp_ms), "recvWindow": "5000"},
    )
    if isinstance(payload, list):
        for row in payload:
            if row.get("symbol") != symbol:
                continue
            side = str(row.get("positionSide", "")).upper().strip()
            if side:
                return side
    return "BOTH"


def _refresh_market_order_status(
    *,
    order: dict[str, Any],
    submit_result: dict[str, Any],
    base_url: str,
    api_key: str,
    api_secret: str,
) -> dict[str, Any]:
    order_id = submit_result.get("exchange_order_id")
    if not order_id or str(order.get("type", "")).upper() != "MARKET":
        return submit_result

    latest = submit_result
    for _ in range(5):
        time.sleep(0.4)
        server_time_ms = _get_binance_server_time()
        local_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        payload = _signed_get(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            path="/fapi/v1/order",
            params={
                "symbol": order["symbol"],
                "orderId": str(order_id),
                "timestamp": str(server_time_ms),
                "recvWindow": "5000",
            },
        )
        request_qty = float(order["quantity"])
        status = str(payload.get("status", latest.get("status")) or "").upper()
        filled_qty = float(payload.get("executedQty") or latest.get("entry_filled_qty") or 0.0)
        partial_fill_detected = 0.0 < filled_qty < request_qty
        has_open_remainder = partial_fill_detected and status in {"NEW", "PARTIALLY_FILLED"}
        order_terminal = status in {"FILLED", "CANCELED", "EXPIRED", "REJECTED"}
        latest = {
            **latest,
            "status": payload.get("status", latest.get("status")),
            "raw": payload,
            "entry_filled_qty": filled_qty,
            "exchange_code": payload.get("code"),
            "exchange_msg": payload.get("msg"),
            "server_time": server_time_ms,
            "local_time": local_time_ms,
            "timestamp_used": server_time_ms,
            "partial_fill_detected": partial_fill_detected,
            "has_open_remainder": has_open_remainder,
            "order_terminal": order_terminal,
        }
        if str(payload.get("status", "")).upper() == "FILLED":
            return latest
    return latest


def _submit_testnet_order(order: dict[str, Any]) -> dict[str, Any]:
    api_key = os.getenv("BINANCE_TESTNET_KEY_PLACEHOLDER", "").strip()
    api_secret = os.getenv("BINANCE_TESTNET_SECRET_PLACEHOLDER", "").strip()
    if not api_key or not api_secret:
        raise HTTPException(status_code=400, detail="testnet credentials missing")

    base_url = _resolve_api_base()
    price = order["price"]
    if price in (None, ""):
        price = _fetch_mark_price(order["symbol"])
    price_value = float(price)

    if order["dry_run"]:
        return {
            "ok": True,
            "dry_run": True,
            "simulated": True,
            "submit_called": True,
            "exchange": "BINANCE_TESTNET",
            "symbol": order["symbol"],
            "side": order["side"],
            "quantity": order["quantity"],
            "reduceOnly": order["reduceOnly"],
            "profile": order["profile"],
            "price": price_value,
            "status": "FILLED",
            "api_base": base_url,
            "trace_id": order["trace_id"],
            "entry_request_qty": float(order["quantity"]),
            "entry_filled_qty": float(order["quantity"]),
            "executed_qty": float(order["quantity"]),
            "exchange_order_id": f"dryrun-{str(order['trace_id'])[:12]}",
            "exchange_code": None,
            "exchange_msg": "DRY_RUN_SIMULATED_FILL",
            "server_time": None,
            "local_time": None,
            "timestamp_used": None,
            "retry_on_1021": False,
            "partial_fill_detected": False,
            "has_open_remainder": False,
            "order_terminal": True,
        }
    local_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    server_time_ms = _get_binance_server_time()
    try:
        result = _submit_once(
            order,
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            price_value=price_value,
            timestamp_ms=server_time_ms,
            local_time_ms=local_time_ms,
        )
        return _refresh_market_order_status(
            order=order,
            submit_result=result,
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        if detail.get("exchange_code") != -1021:
            raise
        retry_local_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        retry_server_time_ms = _get_binance_server_time()
        retry_result = _submit_once(
            order,
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            price_value=price_value,
            timestamp_ms=retry_server_time_ms,
            local_time_ms=retry_local_time_ms,
        )
        retry_result["retry_on_1021"] = True
        retry_result = _refresh_market_order_status(
            order=order,
            submit_result=retry_result,
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
        )
        retry_result["retry_on_1021"] = True
        return retry_result


def _to_str_or_empty(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


async def get_investor_positions_service() -> dict[str, Any]:
    now_mono = time.monotonic()
    cached = _POSITIONS_CACHE.get("value")
    expires_at = float(_POSITIONS_CACHE.get("expires_at", 0.0) or 0.0)
    if isinstance(cached, dict) and now_mono < expires_at:
        return dict(cached)

    _load_runtime_env_defaults()
    api_key = os.getenv("BINANCE_TESTNET_KEY_PLACEHOLDER", "").strip()
    api_secret = os.getenv("BINANCE_TESTNET_SECRET_PLACEHOLDER", "").strip()
    
    # JSON 설정 파일에서 직접 읽기 (fallback)
    if not api_key or not api_secret:
        try:
            root = Path(__file__).resolve().parents[3]
            config_path = root / "config.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    binance_config = config.get("binance_testnet", {})
                    api_key = binance_config.get("api_key", api_key)
                    api_secret = binance_config.get("api_secret", api_secret)
        except Exception:
            pass
    
    if not api_key or not api_secret:
        raise HTTPException(status_code=400, detail="testnet credentials missing")

    base_url = _resolve_api_base()
    server_time_ms = _get_binance_server_time()
    try:
        payload = _signed_get(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            path="/fapi/v2/positionRisk",
            params={"timestamp": str(server_time_ms), "recvWindow": "5000"},
        )
    except Exception as exc:
        return {
            "ok": False,
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": "binance_futures",
            "positions": [],
            "error": str(exc),
        }

    positions: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                continue
            positions.append(
                {
                    "symbol": _to_str_or_empty(row.get("symbol")),
                    "positionAmt": _to_str_or_empty(row.get("positionAmt")),
                    "entryPrice": _to_str_or_empty(row.get("entryPrice")),
                    "markPrice": _to_str_or_empty(row.get("markPrice")),
                    "unRealizedProfit": _to_str_or_empty(row.get("unRealizedProfit")),
                    "positionSide": _to_str_or_empty(row.get("positionSide")),
                    "leverage": _to_str_or_empty(row.get("leverage")),
                    "marginType": _to_str_or_empty(row.get("marginType")),
                    "liquidationPrice": _to_str_or_empty(row.get("liquidationPrice")),
                    "updateTime": _to_str_or_empty(row.get("updateTime")),
                }
            )

    result = {
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "binance_futures",
        "positions": positions,
    }
    _POSITIONS_CACHE["value"] = result
    _POSITIONS_CACHE["expires_at"] = time.monotonic() + _POSITIONS_CACHE_TTL_SEC
    return result


async def get_investor_account_service() -> dict[str, Any]:
    """계좌 자산 정보 가져오기"""
    _load_runtime_env_defaults()
    api_key = os.getenv("BINANCE_TESTNET_KEY_PLACEHOLDER", "").strip()
    api_secret = os.getenv("BINANCE_TESTNET_SECRET_PLACEHOLDER", "").strip()
    
    # JSON 설정 파일에서 자격증명 로드 (fallback)
    if not api_key or not api_secret:
        try:
            config_path = Path(__file__).parent.parent.parent.parent / "config.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                binance_config = config.get("binance_testnet", {})
                api_key = binance_config.get("api_key", api_key)
                api_secret = binance_config.get("api_secret", api_secret)
        except Exception:
            pass
    
    if not api_key or not api_secret:
        return {
            "ok": False,
            "ts": datetime.now(timezone.utc).isoformat(),
            "credentials_present": False,
            "account_equity": "",
            "binance_realtime_link_ok": False,
            "binance_link_status": "NO_CREDENTIALS",
            "api_base": _resolve_api_base(),
            "error": "API credentials not found"
        }
    
    try:
        # 바이낸스 API 서버 시간 가져오기
        server_time_ms = _get_binance_server_time()
        
        # 계좌 정보 API 호출
        payload = _signed_get(
            base_url=_resolve_api_base(),
            api_key=api_key,
            api_secret=api_secret,
            path="/fapi/v2/account",
            params={"timestamp": str(server_time_ms), "recvWindow": "5000"},
        )
        
        if isinstance(payload, dict):
            total_wallet_balance = float(payload.get("totalWalletBalance", "0"))
            total_unrealized_pnl = float(payload.get("totalUnrealizedProfit", "0"))
            total_margin_balance = float(payload.get("totalMarginBalance", "0"))
            account_equity = total_margin_balance  # 계좌 자산 = 마진 잔고
            
            return {
                "ok": True,
                "ts": datetime.now(timezone.utc).isoformat(),
                "credentials_present": True,
                "account_equity": str(account_equity),
                "total_wallet_balance": str(total_wallet_balance),
                "total_unrealized_pnl": str(total_unrealized_pnl),
                "total_margin_balance": str(total_margin_balance),
                "binance_realtime_link_ok": True,
                "binance_link_status": "TESTNET_REALTIME_LINKED",
                "api_base": _resolve_api_base(),
                "source": "binance_futures"
            }
        else:
            return {
                "ok": False,
                "ts": datetime.now(timezone.utc).isoformat(),
                "credentials_present": True,
                "account_equity": "",
                "binance_realtime_link_ok": False,
                "binance_link_status": "API_RESPONSE_ERROR",
                "api_base": _resolve_api_base(),
                "error": "Invalid API response format"
            }
            
    except Exception as exc:
        return {
            "ok": False,
            "ts": datetime.now(timezone.utc).isoformat(),
            "credentials_present": True,
            "account_equity": "",
            "binance_realtime_link_ok": False,
            "binance_link_status": "API_CALL_FAILED",
            "api_base": _resolve_api_base(),
            "error": str(exc)
        }


async def post_investor_order_service(payload: dict[str, Any]) -> dict[str, Any]:
    _load_runtime_env_defaults()
    order = _normalize_order_payload(payload)
    if order.get("action") == "cancel_protection_orders":
        result = _cancel_testnet_protection_orders(order)
        _append_jsonl(
            _runtime_event_path(),
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event_type": "ORDER_API_CANCEL_PROTECTION",
                "trace_id": order["trace_id"],
                "symbol": order["symbol"],
                "client_order_ids": list(order["client_order_ids"]),
                "result_count": len(result.get("results", [])),
                "dry_run": order["dry_run"],
            },
        )
        return result
    audit_row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": "ORDER_API_REQUEST",
        "trace_id": order["trace_id"],
        "client_order_id": order["clientOrderId"],
        "symbol": order["symbol"],
        "side": order["side"],
        "quantity": order["quantity"],
        "type": order["type"],
        "closePosition": order["closePosition"],
        "stopPrice": order["stopPrice"],
        "reduceOnly": order["reduceOnly"],
        "profile": order["profile"],
        "dry_run": order["dry_run"],
        "entry_request_qty": float(order["quantity"]),
        "quantity_before_normalize": order["quantity_before_normalize"],
        "step_size": order["normalization_meta"].get("step_size"),
        "min_qty": order["normalization_meta"].get("min_qty"),
        "min_notional": order["normalization_meta"].get("min_notional"),
        "estimated_price": order["normalization_meta"].get("estimated_price"),
        "estimated_notional": order["normalization_meta"].get("estimated_notional"),
        "min_notional_guard_applied": order["normalization_meta"].get("min_notional_guard_applied", False),
    }
    _append_jsonl(_runtime_event_path(), audit_row)

    cooldown_remaining = _reject_cooldown_remaining(order)
    if cooldown_remaining > 0 and order["reduceOnly"]:
        detail = {
            "submit_called": False,
            "trace_id": order["trace_id"],
            "client_order_id": order["clientOrderId"],
            "status": 409,
            "symbol": order["symbol"],
            "side": order["side"],
            "quantity": order["quantity"],
            "reduceOnly": order["reduceOnly"],
            "entry_request_qty": float(order["quantity"]),
            "entry_filled_qty": 0.0,
            "exchange_code": -4164,
            "exchange_msg": f"REDUCE_ONLY_CONFLICT_SUPPRESSED cooldown_remaining={round(cooldown_remaining, 3)}",
            "server_time": None,
            "local_time": None,
            "timestamp_used": None,
            "partial_fill_detected": False,
            "has_open_remainder": False,
            "order_terminal": True,
        }
        _append_jsonl(
            _runtime_event_path(),
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event_type": "REDUCE_ONLY_CONFLICT",
                "trace_id": order["trace_id"],
                "client_order_id": order["clientOrderId"],
                "symbol": order["symbol"],
                "side": order["side"],
                "quantity": order["quantity"],
                "reduceOnly": order["reduceOnly"],
                "cooldown_remaining_sec": round(cooldown_remaining, 3),
            },
        )
        _append_jsonl(
            _runtime_event_path(),
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event_type": "ORDER_API_RESPONSE",
                **detail,
                "dry_run": order["dry_run"],
            },
        )
        raise HTTPException(status_code=409, detail=detail)

    try:
        result = _submit_testnet_order(order)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        if detail.get("exchange_code") == -4164 and order["reduceOnly"]:
            _set_reject_cooldown(order)
            _append_jsonl(
                _runtime_event_path(),
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "event_type": "REDUCE_ONLY_CONFLICT",
                    "trace_id": order["trace_id"],
                    "client_order_id": order["clientOrderId"],
                    "symbol": order["symbol"],
                    "side": order["side"],
                    "quantity": order["quantity"],
                    "reduceOnly": order["reduceOnly"],
                    "exchange_code": detail.get("exchange_code"),
                    "exchange_msg": detail.get("exchange_msg"),
                    "cooldown_applied_sec": _REJECT_COOLDOWN_TTL_SEC,
                },
            )
        _append_jsonl(
            _runtime_event_path(),
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event_type": "ORDER_API_RESPONSE",
                "trace_id": order["trace_id"],
                "client_order_id": order["clientOrderId"],
                "symbol": order["symbol"],
                "side": order["side"],
                "quantity": order["quantity"],
                "reduceOnly": order["reduceOnly"],
                "status": detail.get("status", exc.status_code),
                "dry_run": order["dry_run"],
                "submit_called": detail.get("submit_called", False),
                "exchange_order_id": detail.get("exchange_order_id"),
                "entry_request_qty": detail.get("entry_request_qty", float(order["quantity"])),
                "entry_filled_qty": detail.get("entry_filled_qty", 0.0),
                "exchange_code": detail.get("exchange_code"),
                "exchange_msg": detail.get("exchange_msg"),
                "server_time": detail.get("server_time"),
                "local_time": detail.get("local_time"),
                "timestamp_used": detail.get("timestamp_used"),
                "partial_fill_detected": detail.get("partial_fill_detected", False),
                "has_open_remainder": detail.get("has_open_remainder", False),
                "order_terminal": detail.get("order_terminal", False),
            },
        )
        raise

    _append_jsonl(
        _runtime_event_path(),
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event_type": "ORDER_API_RESPONSE",
            "trace_id": order["trace_id"],
            "client_order_id": order["clientOrderId"],
            "symbol": order["symbol"],
            "side": order["side"],
            "quantity": order["quantity"],
            "reduceOnly": order["reduceOnly"],
            "status": result.get("status"),
            "dry_run": result.get("dry_run", False),
            "submit_called": result.get("submit_called", False),
            "exchange_order_id": result.get("exchange_order_id"),
            "entry_request_qty": result.get("entry_request_qty"),
            "entry_filled_qty": result.get("entry_filled_qty"),
            "exchange_code": result.get("exchange_code"),
            "exchange_msg": result.get("exchange_msg"),
            "server_time": result.get("server_time"),
            "local_time": result.get("local_time"),
            "timestamp_used": result.get("timestamp_used"),
            "partial_fill_detected": result.get("partial_fill_detected", False),
            "has_open_remainder": result.get("has_open_remainder", False),
            "order_terminal": result.get("order_terminal", False),
        },
    )
    return result
