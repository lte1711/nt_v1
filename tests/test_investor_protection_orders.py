from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.next_trade.api.investor_service import (  # noqa: E402
    _build_submit_payload,
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
        self.assertEqual(params["closePosition"], "true")
        self.assertEqual(params["positionSide"], "LONG")
        self.assertEqual(params["stopPrice"], "59000.0")
        self.assertEqual(params["workingType"], "MARK_PRICE")
        self.assertNotIn("quantity", params)
        self.assertNotIn("reduceOnly", params)

    def test_investor_routes_expose_open_orders_and_ops_positions_alias(self) -> None:
        script = (ROOT / "src" / "next_trade" / "api" / "routes_v1_investor.py").read_text(encoding="utf-8")

        self.assertIn('@router.get("/api/v1/trading/open-orders")', script)
        self.assertIn('@router.get("/api/v1/ops/positions")', script)


if __name__ == "__main__":
    unittest.main()
