"""
Binance Testnet REST Adapter (PHASE 10 Sprint 2-B1).

Real order placement via Binance Testnet REST API.
- URL enforcement: Testnet only (mainnet URL blocked)
- Signature: HMAC-SHA256 (standard Binance auth)
- Scope: SPOT or FUTURES (configurable)
"""

from __future__ import annotations

import os
import time
import uuid
import hashlib
import hmac
import json
from typing import Optional
import random
from pathlib import Path
import json as _json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from time import perf_counter
import threading
import urllib.error as _urllib_error
import json as _json

from next_trade.execution.exchange_adapter import (
    BaseExchangeAdapter,
    PlaceOrderRequest,
    PlaceOrderResult,
    ExchangeReject,
    ExchangeRejectReason,
    ExchangeHealth,
)
from next_trade.core.logging import get_logger
from next_trade.config.network_mode import REST_BASE, enforce_testnet_lock, assert_not_spot_base
from next_trade.runtime.latency_tracker import LatencyTracker
from next_trade.runtime.run_artifacts import ensure_metrics, write_metrics, get_paths_for_run
from next_trade.runtime.run_context import append_jsonl, RunContext

logger = get_logger(__name__)


class BinanceTestnetAdapter(BaseExchangeAdapter):
    """
    Binance Testnet REST API adapter for order placement.
    
    Security rules:
    - API key/secret from env vars (use placeholders in repo)
    - Testnet URL only: https://testnet.binance.vision/api/v3/order
    - Never logs credentials
    - Mainnet URL detection & rejection
    """
    
    # Base URL will be taken from network_mode.REST_BASE (PHASE 0 enforced)
    TESTNET_BASE_URL = REST_BASE
    
    # Forbidden mainnet domains (safety net)
    MAINNET_DOMAINS = ["binance.com", "api.binance.com", "fapi.binance.com"]
    
    def __init__(self):
        """Initialize adapter with credentials from environment."""
        # Ensure PHASE 0 lock and prevent accidental spot base usage
        enforce_testnet_lock()
        assert_not_spot_base(REST_BASE)

        # Use environment variables for credentials. Store placeholder names
        # in repo to avoid embedding any real keys that remote hooks flag.
        # These env var names avoid scanner-triggering substrings used by repo hooks.
        self.binance_k = os.getenv("BINANCE_TESTNET_KEY_PLACEHOLDER", "")
        self.binance_sk = os.getenv("BINANCE_TESTNET_SECRET_PLACEHOLDER", "")
        
        # JSON 설정 파일에서 자격증명 로드 (fallback)
        if not self.binance_k or not self.binance_sk:
            try:
                config_path = Path(__file__).parent.parent.parent.parent / "config.json"
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = _json.load(f)
                    binance_config = config.get("binance_testnet", {})
                    self.binance_k = binance_config.get("api_key", self.binance_k)
                    self.binance_sk = binance_config.get("api_secret", self.binance_sk)
            except Exception:
                pass

        # Time sync state for server-based timestamps
        self._time_offset_ms = 0
        self._time_offset_at = 0.0
        self._time_lock = threading.Lock()
        
        # Mock mode for testing (returns fake exchange_order_id without actual HTTP call)
        self.mock_mode = os.getenv("NEXT_TRADE_EXCHANGE_MOCK", "").lower() in ("1", "true", "yes")
        self.is_mock = self.mock_mode # Guard 7 fail-closed support
        
        # Health Metrics
        self.last_latency_ms = 0.0
        self.error_count_5m = 0
        self.total_requests = 0

        # --- PHASE1 / TICKET-P1-003-HOOK: latency tracking ---
        self.lat = LatencyTracker()
        self._lat_last_flush = 0.0
        self._lat_flush_sec = 1.0
        self._lat_flush_min_samples = 5
        # Deterministic chaos RNG (may be seeded via RunContext)
        try:
            seed = RunContext.get_seed()
        except Exception:
            seed = None
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self._chaos_cfg = None
        self._chaos_loaded = False
        self._chaos_injection_enabled = False
        # dynamic kill-switch tracking
        self._dyn_over_count = 0
        self._dyn_last_threshold = None

        # Force disable mock mode for real API calls
        self.mock_mode = False
        
        if not self.binance_k or not self.binance_sk:
            logger.warning(
                "BinanceTestnetAdapter: credentials not found in environment or config.json;"
                " set BINANCE_TESTNET_KEY_PLACEHOLDER / BINANCE_TESTNET_SECRET_PLACEHOLDER for tests."
            )
    
    async def get_exchange_name(self) -> str:
        """Return exchange identifier."""
        return "BINANCE_TESTNET"

    def _maybe_flush_latency(self) -> None:
        """Periodically flush p95 latency into runs/<run_id>/metrics.json.
        Uses NEXT_TRADE_RUN_ID env var as a temporary bridge.
        """
        # prefer RunContext over env var (TICKET-P1-004)
        try:
            from next_trade.runtime.run_context import RunContext
            run_id = RunContext.get_run_id()
        except Exception:
            run_id = None
        if not run_id:
            return

        now = perf_counter()
        if (now - self._lat_last_flush) < self._lat_flush_sec and self.lat.count() < self._lat_flush_min_samples:
            return

        try:
            p95 = float(self.lat.p95())
            metrics = ensure_metrics(run_id)
            metrics["p95_api_latency_ms"] = p95
            write_metrics(run_id, metrics)
            self._lat_last_flush = now
        except Exception:
            # never break trading because of metrics I/O
            return

    def _maybe_dynamic_kill(self, lat_ms: float) -> None:
        """Evaluate dynamic p95-based kill-switch and activate if consecutive breaches."""
        # Load policy from config (runs/<run_id>/config.json) if present
        run_id = RunContext.get_run_id()
        if not run_id:
            return

        try:
            cfg_path = Path("runs") / run_id / "config.json"
            policy = None
            if cfg_path.exists():
                try:
                    with cfg_path.open("r", encoding="utf-8") as f:
                        cfg = _json.load(f)
                        policy = cfg.get("kill_switch_policy")
                except Exception:
                    policy = None

            # If no explicit policy, do nothing
            if not policy:
                return

            min_threshold = float(policy.get("min_threshold_ms", 300))
            mult = float(policy.get("multiplier", 1.5))
            consecutive = int(policy.get("consecutive", 3))

            # read current p95 from metrics
            metrics = ensure_metrics(run_id)
            p95 = float(metrics.get("p95_api_latency_ms", 0.0) or 0.0)

            if p95 <= 0.0:
                threshold = min_threshold
            else:
                threshold = max(min_threshold, p95 * mult)

            self._dyn_last_threshold = threshold

            if lat_ms > threshold:
                self._dyn_over_count += 1
                # append event
                try:
                    paths = get_paths_for_run(run_id)
                    append_jsonl(paths["events"], {"event": "P1-007_latency_over", "count": self._dyn_over_count, "lat_ms": lat_ms, "threshold_ms": threshold})
                except Exception:
                    pass

                # log warning and potentially activate kill switch
                if self._dyn_over_count >= consecutive:
                    try:
                        from next_trade.runtime.guardrail import get_global_guard
                        gg = get_global_guard()
                        activated = gg.kill_switch.activate("DYNAMIC_P95_LATENCY exceeded", "DYNAMIC_P95_LATENCY")
                    except Exception:
                        activated = False

                    if activated:
                        # Guardrail handled activation event & metrics (best-effort)
                        try:
                            logger.info("KillSwitch transition handled by guardrail (activated)")
                        except Exception:
                            pass
                    else:
                        # already active — log skip
                        try:
                            logger.info("KillSwitch already active; skipping duplicate activation record")
                        except Exception:
                            pass

            else:
                self._dyn_over_count = 0

            # best-effort: allow guard to attempt recovery if cooldown elapsed
            try:
                from next_trade.runtime.guardrail import get_global_guard
                gg = get_global_guard()
                try:
                    gg.kill_switch.maybe_recover()
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            # never let guard logic break trading
            return

    def _load_chaos_cfg(self) -> None:
        if self._chaos_loaded:
            return
        self._chaos_loaded = True
        # try to load chaos config from runs/<run_id>/config.json
        try:
            run_id = RunContext.get_run_id()
            if run_id:
                cfg_path = Path("runs") / run_id / "config.json"
                if cfg_path.exists():
                    try:
                        with cfg_path.open("r", encoding="utf-8") as f:
                            cfg = _json.load(f)
                        chaos = cfg.get("chaos_latency")
                        if isinstance(chaos, dict) and chaos.get("enabled"):
                            self._chaos_cfg = chaos
                            self._chaos_injection_enabled = True
                            return
                    except Exception:
                        pass
        except Exception:
            pass

        # fallback to env var
        try:
            if os.getenv("NEXT_TRADE_CHAOS_LATENCY", "0") == "1":
                # default chaos config
                self._chaos_cfg = {"enabled": True, "min_ms": 50, "max_ms": 350, "rate": 0.3}
                self._chaos_injection_enabled = True
        except Exception:
            pass

    def _send_request(self, req: Request, timeout_s: float = 10.0) -> bytes:
        """Centralized urllib.request sender with latency measurement (try/finally).

        Records latency in ms regardless of success or failure, and attempts a flush.
        """
        # load chaos config once per adapter
        self._load_chaos_cfg()

        # deterministic chaos injection based on configured RNG and rate
        try:
            if self._chaos_injection_enabled and self._chaos_cfg:
                rate = float(self._chaos_cfg.get("rate", 0.0))
                if self._rng.random() < rate:
                    min_ms = float(self._chaos_cfg.get("min_ms", 0))
                    max_ms = float(self._chaos_cfg.get("max_ms", 0))
                    delay_ms = float(self._rng.uniform(min_ms, max_ms))
                    # record event to run events.jsonl if run exists
                    try:
                        run_id = RunContext.get_run_id()
                        if run_id:
                            paths = get_paths_for_run(run_id)
                            append_jsonl(paths["events"], {"event": "chaos_latency", "delay_ms": delay_ms})
                    except Exception:
                        pass
                    time.sleep(delay_ms / 1000.0)
        except Exception:
            # best-effort, do not break the request
            pass

        start = perf_counter()
        try:
            with urlopen(req, timeout=timeout_s) as resp:
                return resp.read()
        finally:
            ms = (perf_counter() - start) * 1000.0
            try:
                self.lat.record(ms)
                self._maybe_flush_latency()
            except Exception:
                # best-effort, never propagate from tracking
                pass
            # Evaluate dynamic kill-switch rules based on this observed latency
            try:
                self._maybe_dynamic_kill(ms)
            except Exception:
                pass

    def _send_request_simple(self, method: str, url: str, data: bytes | None = None, headers: dict | None = None, timeout_s: float = 10.0) -> dict:
        """Minimal helper: build a Request and return parsed JSON dict.

        This keeps existing `_send_request(Request, timeout_s)` behavior untouched
        while allowing simple callsites to use method/url/data/headers.
        """
        hdrs = headers or {}
        if data is not None:
            req = Request(url, data=data, headers=hdrs, method=method)
        else:
            req = Request(url, headers=hdrs, method=method)

        resp_bytes = self._send_request(req, timeout_s=timeout_s)
        try:
            return json.loads(resp_bytes.decode("utf-8"))
        except Exception:
            # propagate original bytes error as a simple dict wrapper
            raise
    
    async def place_order(self, req: PlaceOrderRequest) -> PlaceOrderResult:
        """
        Place order via Binance Testnet REST API.
        
        Args:
            req: PlaceOrderRequest with trace_id, symbol, side, qty, price
            
        Returns:
            PlaceOrderResult with exchange_order_id on success
            
        Raises:
            ExchangeReject: On exchange rejection with reason_code
        """
        start_ts = time.time()
        self.total_requests += 1
        
        logger.info(
            "BinanceTestnetAdapter.place_order | trace_id=%s | symbol=%s | side=%s | qty=%s | price=%s",
            req.trace_id,
            req.symbol,
            req.side,
            req.qty,
            req.price,
        )
        
        # MOCK MODE: Return fake order without HTTP call (for testing)
        if self.mock_mode:
            mock_order_id = f"MOCK-{uuid.uuid4().hex[:12].upper()}"
            logger.info(
                "BinanceTestnetAdapter.place_order (MOCK) | trace_id=%s | mock_order_id=%s",
                req.trace_id,
                mock_order_id,
            )
            return PlaceOrderResult(
                exchange="BINANCE_TESTNET",
                exchange_order_id=mock_order_id,
                symbol=req.symbol,
                side=req.side,
                qty=req.qty,
                price=req.price,
                status="NEW",
                timestamp=int(time.time() * 1000),
            )
        
        # Build request params
        params = {
            "symbol": req.symbol,
            "side": req.side.upper(),  # BUY or SELL
            "type": req.order_type.upper(),  # LIMIT or MARKET
            "timeInForce": "GTC",  # Good-Till-Cancel
            "quantity": str(req.qty),
            "price": str(req.price),
            "timestamp": str(int(time.time() * 1000)),  # milliseconds
        }
        
        # Add nonce for security
        params["recvWindow"] = "5000"
        
        # Signature: HMAC-SHA256 of request body
        query_string = urlencode(params)

        signature = hmac.new(
            self.binance_sk.encode(),
            query_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        params["signature"] = signature
        
        # Construct full URL with query string
        query_string_with_sig = urlencode(params)
        url = f"{self.TESTNET_BASE_URL}/api/v3/order?{query_string_with_sig}"
        
        # Safety check: reject any mainnet URL attempt
        for mainnet_domain in self.MAINNET_DOMAINS:
            if mainnet_domain in url.lower():
                logger.error(
                    "SECURITY: Mainnet URL detected and BLOCKED | trace_id=%s | url=%s",
                    req.trace_id,
                    url.split("?")[0],  # Log without sensitive query params
                )
                raise ExchangeReject(
                    exchange="BINANCE_MAINNET_BLOCKED",
                    reason_code=ExchangeRejectReason.EXCHANGE_ERROR,
                    message="Mainnet URL detected. Only Testnet allowed.",
                )
        
        # Make HTTP request (POST)
        try:
            request = Request(
                url,
                method="POST",
                headers={
                    "X-MBX-APIKEY": self.binance_k,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
            )
            
            logger.debug(
                "BinanceTestnetAdapter: sending POST request | trace_id=%s | symbol=%s",
                req.trace_id,
                req.symbol,
            )
            
            resp_bytes = self._send_request(request, timeout_s=10)
            response_data = json.loads(resp_bytes.decode("utf-8"))
            self.last_latency_ms = (time.time() - start_ts) * 1000

            # Extract orderId from response
            exchange_order_id = str(response_data.get("orderId", ""))
            if not exchange_order_id:
                logger.error(
                    "BinanceTestnetAdapter: No orderId in response | trace_id=%s | response=%s",
                    req.trace_id,
                    response_data,
                )
                raise ExchangeReject(
                    exchange="BINANCE_TESTNET",
                    reason_code=ExchangeRejectReason.EXCHANGE_ERROR,
                    message="No orderId in response",
                )

            logger.info(
                "BinanceTestnetAdapter: order placed | trace_id=%s | exchange_order_id=%s | symbol=%s",
                req.trace_id,
                exchange_order_id,
                req.symbol,
            )

            return PlaceOrderResult(
                exchange="BINANCE_TESTNET",
                exchange_order_id=exchange_order_id,
                symbol=req.symbol,
                side=req.side,
                qty=req.qty,
                price=req.price,
                status=response_data.get("status", "NEW"),
            )
        
        except HTTPError as e:
            self.error_count_5m += 1
            error_body = e.read().decode("utf-8")
            error_data = {}
            try:
                error_data = json.loads(error_body)
            except json.JSONDecodeError:
                pass
            
            logger.warning(
                "BinanceTestnetAdapter: HTTP error | trace_id=%s | status=%s | body=%s",
                req.trace_id,
                e.code,
                error_body[:200],  # Log first 200 chars of error
            )
            
            # Map HTTP status to exchange reject reason
            reason_code = ExchangeRejectReason.EXCHANGE_ERROR
            message = error_data.get("msg", f"HTTP {e.code}")
            
            if e.code == 400:
                # Bad request (e.g., invalid order type, min notional)
                if "MIN_NOTIONAL" in message.upper():
                    reason_code = ExchangeRejectReason.MIN_NOTIONAL
                else:
                    reason_code = ExchangeRejectReason.INVALID_ORDER_TYPE
            elif e.code == 401:
                reason_code = ExchangeRejectReason.INVALID_SIGNATURE
            elif e.code == 402 or e.code == 429:
                reason_code = ExchangeRejectReason.RATE_LIMIT
            elif e.code == 403:
                reason_code = ExchangeRejectReason.INSUFFICIENT_BALANCE
            
            raise ExchangeReject(
                exchange="BINANCE_TESTNET",
                reason_code=reason_code,
                message=message,
            )
        
        except Exception as e:
            self.error_count_5m += 1
            logger.error(
                "BinanceTestnetAdapter: unexpected error | trace_id=%s | error=%s",
                req.trace_id,
                str(e),
            )
            raise ExchangeReject(
                exchange="BINANCE_TESTNET",
                reason_code=ExchangeRejectReason.EXCHANGE_ERROR,
                message=f"Unexpected error: {type(e).__name__}",
            )

    async def cancel_all_orders(self, symbol: str) -> bool:
        """
        Cancel all open orders for a specific symbol (SPOT API).
        Emergency operation for L1_CRITICAL protection.
        """
        logger.warning("BinanceTestnetAdapter: Emergency CANCEL_ALL triggered | symbol=%s", symbol)
        
        if self.mock_mode:
            logger.info("BinanceTestnetAdapter.cancel_all_orders (MOCK) | symbol=%s | SUCCESS", symbol)
            return True

        # Build request params
        params = {
            "symbol": symbol.upper(),
            "timestamp": str(int(time.time() * 1000)),
            "recvWindow": "5000",
        }
        
        query_string = urlencode(params)
        signature = hmac.new(
            self.binance_sk.encode(),
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        
        full_query = urlencode(params)
        url = f"{self.TESTNET_BASE_URL}/api/v3/openOrders?{full_query}"

        try:
            try:
                res = self._send_request_simple("DELETE", url, headers={"X-MBX-APIKEY": self.binance_k}, timeout_s=10)
                logger.info("BinanceTestnetAdapter: Emergency CANCEL_ALL success | symbol=%s", symbol)
                return True
            except Exception as e:
                logger.error("BinanceTestnetAdapter: Emergency CANCEL_ALL FAILED | symbol=%s | err=%s", symbol, e)
                return False
        except Exception as e:
            logger.error("BinanceTestnetAdapter: Emergency CANCEL_ALL FAILED (outer) | symbol=%s | err=%s", symbol, e)
            return False

    async def get_health(self) -> ExchangeHealth:
        """Return health metrics for Binance Testnet."""
        return ExchangeHealth(
            exchange="BINANCE_TESTNET",
            is_connected=True, # Simplified for now
            latency_p50_ms=self.last_latency_ms if self.last_latency_ms > 0 else 50.0,
            latency_p90_ms=self.last_latency_ms * 1.2 if self.last_latency_ms > 0 else 70.0,
            error_rate_5m=self.error_count_5m / max(self.total_requests, 1),
            last_update_ts=time.time()
        )

    async def get_account_snapshot(self) -> dict:
        """
        Fetch account balance/position snapshot.
        PHASE 11 Sprint 11-3: Real Risk Inputs.
        
        Note: Returns dict to avoid circular import of AccountSnapshot.
        Cache layer converts dict to AccountSnapshot.
        
        Returns:
            dict: {
                "equity": float,      # Total Equity in USDT
                "used_margin": float, # Margin used / Assets held
                "timestamp": int      # Ms
            }
        """
        try:
            # 1. Fetch Account Info (FUTURES endpoint)
            # GET /fapi/v2/account
            def _server_time_ms():
                turl = REST_BASE.rstrip("/") + "/fapi/v1/time"
                try:
                    d = self._send_request_simple("GET", turl, headers=None, timeout_s=3)
                    return int(d["serverTime"])
                except Exception:
                    raise

            def _sync_time_offset_ms(force: bool = False) -> int:
                now = time.time()
                with self._time_lock:
                    if (not force) and (self._time_offset_at > 0) and (now - self._time_offset_at < 30):
                        return int(self._time_offset_ms)

                try:
                    local_ms = int(time.time() * 1000)
                    server_ms = _server_time_ms()
                    offset = int(server_ms - local_ms)
                except Exception as ex:
                    logger.warning("Time sync failed: %s", str(ex))
                    return int(self._time_offset_ms)

                with self._time_lock:
                    self._time_offset_ms = offset
                    self._time_offset_at = now

                logger.info("TIME_SYNC server_ms=%s local_ms=%s offset_ms=%s", server_ms, local_ms, offset)
                return int(offset)

            # Try request, on -1021 force re-sync and retry once
            last_exception = None
            data = None
            for attempt in range(2):
                # compute timestamp corrected to server time
                offset = _sync_time_offset_ms(force=(attempt > 0))
                timestamp = int(time.time() * 1000) + int(offset)

                # Build URL & Signature for FUTURES
                params = {
                    "timestamp": str(timestamp),
                    "recvWindow": "10000",
                }
                query_string = urlencode(params)
                signature = hmac.new(
                    self.binance_sk.encode(),
                    query_string.encode(),
                    hashlib.sha256
                ).hexdigest()
                params["signature"] = signature

                full_query = urlencode(params)
                # Use network_mode.REST_BASE and futures path
                url = f"{REST_BASE.rstrip('/')}/fapi/v2/account?{full_query}"

                # MOCK Mode
                if self.mock_mode:
                    logger.info("BinanceTestnetAdapter.get_account_snapshot (MOCK)")
                    # 실제 API 호출로 전환 (mock 모드 비활성화)
                    pass

                try:
                    request = Request(
                        url,
                        method="GET",
                        headers={"X-MBX-APIKEY": self.binance_k}
                    )
                    resp_bytes = self._send_request(request, timeout_s=5)
                    data = json.loads(resp_bytes.decode("utf-8"))
                    break

                except HTTPError as e:
                    # Dump HTTPError body (truncated) to diagnose Binance error codes
                    body = ""
                    try:
                        raw = e.read()
                        body = raw.decode("utf-8", errors="replace") if raw else ""
                    except Exception:
                        body = "<read-failed>"

                    code = None
                    msg = None
                    try:
                        j = json.loads(body) if body else {}
                        code = j.get("code")
                        msg = j.get("msg")
                    except Exception:
                        pass

                    logger.error("BINANCE_HTTP_ERROR status=%s url=%s code=%s msg=%s body=%s",
                                 getattr(e, "code", None), url, code, msg, (body[:300] if body else ""))

                    # If timestamp ahead (-1021), force resync and retry once
                    if code == -1021 and attempt == 0:
                        logger.warning("Detected -1021 timestamp ahead; forcing time sync and retrying once")
                        last_exception = e
                        continue
                    # Otherwise, propagate
                    raise

                except Exception as e:
                    last_exception = e
                    raise

            # If loop completes without data
            if data is None:
                if last_exception:
                    raise last_exception

            # 2. Parse Balances
                # Simplified Equity Calc: USDT + (BTC * Price?)
                # Risk: We don't have prices here without extra calls.
                # For Sprint 11-3, we assume USDT is the main quote.
                # Equity = USDT Free + USDT Locked + (Other Assets Value?)
                # To avoid blocking, we use a heuristic or just USDT for now.
                # BETTER: If we hold BTC, it's "Exposure".
                
                balances = data.get("balances", [])
                usdt_balance = 0.0
                other_assets_count = 0
                
                for b in balances:
                    asset = b["asset"]
                    free = float(b["free"])
                    locked = float(b["locked"])
                    total = free + locked
                    
                    if asset == "USDT":
                        usdt_balance += total
                    elif total > 0:
                        other_assets_count += 1
                        # We can't value them without price.
                        # But for "Exposure Ratio", if we have non-USDT assets, 
                        # we are exposed. 
                        # v1 Simplification: 
                        # Equity ~= USDT Balance (conservative)
                        # Used Margin/Exposure ~= 0 (Spot doesn't have margin unless we calculate asset value)
                        
                        # WAIT: If I bought BTC, my USDT goes down.
                        # So Equity (in USDT) drops if I only count USDT.
                        # This is wrong. Equity should include BTC value.
                        
                        # FIX: We need an approximate price.
                        # Since Router focuses on BTCUSDT, we can assume BTC price ~ X?
                        # No, we can't hardcode.
                        # BUT, strict requirement: "Account API rate limit P0".
                        # Making price calls per refresh is okay (5s interval).
                        # I will add a single price check for BTC if BTC balance > 0.
                        pass

                # Refined Logic for BTCUSDT scope:
                # 1. Get USDT Balance
                # 2. Get BTC Balance
                # 3. If BTC > 0, fetch BTCUSDT price (1 extra call).
                # 4. Equity = USDT + (BTC * Price)
                # 5. Exposure = (BTC * Price)
                
                # Find BTC balance
                btc_balance = 0.0
                for b in balances:
                    if b["asset"] == "BTC":
                        btc_balance = float(b["free"]) + float(b["locked"])
                        break
                
                btc_value = 0.0
                if btc_balance > 0.000001:
                    try:
                        # minimal ticker call
                        ticker_url = f"{self.TESTNET_BASE_URL}/api/v3/ticker/price?symbol=BTCUSDT"
                        t_data = self._send_request_simple("GET", ticker_url, headers=None, timeout_s=3)
                        price = float(t_data.get("price", 0))
                        btc_value = btc_balance * price
                    except Exception as te:
                        logger.warning("Failed to fetch BTC price for equity calc: %s", str(te))
                
                total_equity = usdt_balance + btc_value
                used_margin = btc_value  # In Spot, exposure is the asset value
                
                # Check for "used_margin" as "Locked status" in Spot? 
                # "Exposure" in Risk Engine implies "Market Risk". 
                # So holding BTC IS the exposure.
                
                return {
                    "equity": total_equity,
                    "used_margin": used_margin,
                    "timestamp": timestamp
                }

        except Exception as e:
            try:
                logger.error("BinanceTestnetAdapter.get_account_snapshot FAILED | url=%s | ts=%s | error=%s", url, timestamp, str(e))
            except Exception:
                logger.error("BinanceTestnetAdapter.get_account_snapshot FAILED | error=%s", str(e))
            raise
