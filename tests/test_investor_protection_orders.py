from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import src.next_trade.api.investor_service as investor_service  # noqa: E402
from src.next_trade.api.investor_service import (  # noqa: E402
    _build_market_fallback_limit_order,
    _build_submit_payload,
    _is_algo_order_type,
    _normalize_order_payload,
)


class InvestorProtectionOrderTests(unittest.TestCase):
    def test_normalize_close_position_take_profit_market(self) -> None:
        order = _normalize_order_payload(
            {
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "TAKE_PROFIT_MARKET",
                "closePosition": True,
                "stopPrice": 65000,
                "workingType": "MARK_PRICE",
                "trace_id": "tp-case",
            }
        )

        self.assertEqual(order["type"], "TAKE_PROFIT_MARKET")
        self.assertTrue(order["closePosition"])
        self.assertEqual(order["stopPrice"], 65000.0)
        self.assertEqual(order["workingType"], "MARK_PRICE")
        self.assertEqual(order["quantity"], 0.0)

    def test_build_submit_payload_for_close_position_stop_market(self) -> None:
        params = _build_submit_payload(
            {
                "symbol": "BTCUSDT",
                "side": "SELL",
                "type": "STOP_MARKET",
                "quantity": 0.0,
                "clientOrderId": "sl-case",
                "reduceOnly": False,
                "closePosition": True,
                "stopPrice": 59000.0,
                "workingType": "MARK_PRICE",
            },
            timestamp_ms=1234567890,
            price_value=60000.0,
            position_side="LONG",
        )

        self.assertEqual(params["type"], "STOP_MARKET")
        self.assertEqual(params["algoType"], "CONDITIONAL")
        self.assertEqual(params["clientAlgoId"], "sl-case")
        self.assertEqual(params["closePosition"], "true")
        self.assertEqual(params["positionSide"], "LONG")
        self.assertEqual(params["triggerPrice"], "59000.0")
        self.assertEqual(params["workingType"], "MARK_PRICE")
        self.assertNotIn("quantity", params)
        self.assertNotIn("reduceOnly", params)
        self.assertNotIn("stopPrice", params)

    def test_build_submit_payload_for_standard_market_stays_on_regular_order_api(self) -> None:
        params = _build_submit_payload(
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": "MARKET",
                "quantity": 0.01,
                "clientOrderId": "entry-case",
                "reduceOnly": False,
                "closePosition": False,
                "stopPrice": None,
                "workingType": "MARK_PRICE",
            },
            timestamp_ms=1234567890,
            price_value=60000.0,
            position_side="BOTH",
        )

        self.assertEqual(params["newClientOrderId"], "entry-case")
        self.assertNotIn("clientAlgoId", params)
        self.assertNotIn("algoType", params)
        self.assertEqual(params["quantity"], "0.01")

    def test_algo_order_type_detection(self) -> None:
        self.assertTrue(_is_algo_order_type("STOP_MARKET"))
        self.assertTrue(_is_algo_order_type("TAKE_PROFIT"))
        self.assertFalse(_is_algo_order_type("MARKET"))

    def test_market_fallback_limit_order_uses_ioc_and_tick_rounded_price(self) -> None:
        original = investor_service._fetch_symbol_filters
        investor_service._fetch_symbol_filters = lambda **_: (1.0, 1.0, 5.0, 0.00001)
        try:
            fallback = _build_market_fallback_limit_order(
                {
                    "symbol": "QUICKUSDT",
                    "side": "BUY",
                    "type": "MARKET",
                    "quantity": 446.0,
                    "clientOrderId": "pmx-test",
                },
                base_url="https://demo-fapi.binance.com",
                price_value=0.01193,
            )
        finally:
            investor_service._fetch_symbol_filters = original

        self.assertEqual(fallback["type"], "LIMIT")
        self.assertEqual(fallback["timeInForce"], "IOC")
        self.assertEqual(fallback["price"], 0.01195)
        self.assertEqual(fallback["clientOrderId"], "pmx-test-ioc")

    def test_investor_routes_expose_open_orders_and_ops_positions_alias(self) -> None:
        script = (ROOT / "src" / "next_trade" / "api" / "routes_v1_investor.py").read_text(encoding="utf-8")

        self.assertIn('@router.get("/api/v1/trading/open-orders")', script)
        self.assertIn('@router.get("/api/v1/ops/positions")', script)


if __name__ == "__main__":
    unittest.main()
