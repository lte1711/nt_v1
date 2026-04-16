from __future__ import annotations

import sys
import tempfile
import unittest
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "ops"))

import tools.ops.profitmax_v1_runner as profitmax_runner_module  # noqa: E402
from tools.ops.profitmax_v1_runner import (  # noqa: E402
    ProfitMaxV1Runner,
    RunnerConfig,
    _normalize_trade_outcome_payload,
    build_allocation_top_from_snapshot,
    normalize_allocations,
)
from tools.multi5.run_multi5_engine import (  # noqa: E402
    apply_symbol_diversity_penalty,
    collect_signal_target_symbols,
    collect_recent_blocked_symbols,
    recover_missing_position_workers,
)
from tools.multi5.multi5_symbol_ranker import select_top_one  # noqa: E402
from tools.multi5.multi5_symbol_scanner import build_symbol_state  # noqa: E402


class AllocationRuntimeFixTests(unittest.TestCase):
    def test_apply_symbol_diversity_penalty_reduces_repeated_active_symbol_score(self) -> None:
        adjusted = apply_symbol_diversity_penalty(
            [
                {
                    "symbol": "DOGEUSDT",
                    "edge_score": 1.05,
                    "strategy_signal": "SHORT",
                    "strategy_signal_score": 0.92,
                },
                {
                    "symbol": "ETHUSDT",
                    "edge_score": 0.91,
                    "strategy_signal": "SHORT",
                    "strategy_signal_score": 0.88,
                },
            ],
            recent_selected_symbols=[
                "DOGEUSDT",
                "DOGEUSDT",
                "DOGEUSDT",
                "ETHUSDT",
            ],
            active_symbols={"DOGEUSDT"},
            recent_blocked_symbols={"DOGEUSDT": 5},
        )

        by_symbol = {row["symbol"]: row for row in adjusted}
        self.assertAlmostEqual(by_symbol["DOGEUSDT"]["blocked_symbol_penalty"], 0.6, places=6)
        self.assertAlmostEqual(by_symbol["DOGEUSDT"]["diversification_penalty"], 1.08, places=6)
        self.assertAlmostEqual(by_symbol["DOGEUSDT"]["edge_score"], 0.0, places=6)
        self.assertEqual(by_symbol["DOGEUSDT"]["strategy_signal"], "HOLD")
        self.assertTrue(by_symbol["DOGEUSDT"]["selection_neutralized"])
        self.assertAlmostEqual(by_symbol["DOGEUSDT"]["strategy_signal_score"], -0.16, places=6)
        self.assertAlmostEqual(by_symbol["ETHUSDT"]["diversification_penalty"], 0.08, places=6)

    def test_collect_recent_blocked_symbols_counts_short_bias_guard_events(self) -> None:
        now = datetime.now(timezone.utc)
        rows = [
            {
                "ts": (now - timedelta(minutes=3)).isoformat(),
                "event_type": "ENTRY_TO_SUBMIT_BLOCKED",
                "payload": {"symbol": "DOGEUSDT", "detail": "short_bias_guard"},
            },
            {
                "ts": (now - timedelta(minutes=2)).isoformat(),
                "event_type": "STRATEGY_BLOCKED",
                "payload": {"symbol": "DOGEUSDT", "reason": "short_bias_guard"},
            },
            {
                "ts": (now - timedelta(minutes=2)).isoformat(),
                "event_type": "ENTRY_TO_SUBMIT_BLOCKED",
                "payload": {"symbol": "ETHUSDT", "detail": "entry_quality_score_below_threshold"},
            },
            {
                "ts": (now - timedelta(minutes=30)).isoformat(),
                "event_type": "ENTRY_TO_SUBMIT_BLOCKED",
                "payload": {"symbol": "DOGEUSDT", "detail": "short_bias_guard"},
            },
        ]

        with patch(
            "tools.multi5.run_multi5_engine.read_recent_jsonl_rows",
            lambda path: rows,
        ):
            blocked = collect_recent_blocked_symbols(window_minutes=20)

        self.assertEqual(blocked, {"DOGEUSDT": 2})

    def test_select_top_one_preserves_penalty_fields(self) -> None:
        top = select_top_one(
            [
                {
                    "symbol": "DOGEUSDT",
                    "edge_score": 0.7,
                    "volatility": 0.03,
                    "strategy_signal": "SHORT",
                    "strategy_signal_score": 0.5,
                    "strategy_id": "momentum_intraday_v1",
                    "diversification_penalty": 0.24,
                    "blocked_symbol_penalty": 0.36,
                }
            ]
        )

        self.assertIsNotNone(top)
        self.assertEqual(top["SELECTED_SYMBOL"], "DOGEUSDT")
        self.assertAlmostEqual(top["diversification_penalty"], 0.24, places=6)
        self.assertAlmostEqual(top["blocked_symbol_penalty"], 0.36, places=6)

    def test_build_symbol_state_can_emit_reactive_long_signal(self) -> None:
        closes_1m = [
            100.0, 100.02, 100.04, 100.03, 100.01, 99.98, 99.95, 99.92, 99.88, 99.84,
            99.8, 99.78, 99.74, 99.71, 99.67, 99.62, 99.58, 99.55, 99.51, 99.48,
            99.42, 99.36, 99.28, 99.15, 99.0, 98.8, 98.4, 97.8, 96.7, 95.7,
        ]
        volumes_1m = [1000.0] * 26 + [1600.0, 1800.0, 2200.0, 2600.0]
        closes_5m = [
            100.0, 100.05, 100.02, 100.01, 100.04, 100.0, 99.98, 100.01, 100.03, 100.0,
            99.99, 100.02, 100.01, 100.0, 100.03, 100.01, 99.99, 100.0, 100.02, 100.01,
            100.0, 100.01, 99.98, 100.0, 100.01, 99.99, 100.0, 100.02, 100.01, 100.0,
        ]
        volumes_5m = [5000.0] * len(closes_5m)

        with patch("tools.multi5.multi5_symbol_scanner._resolve_time_window", return_value="ACTIVE"):
            state = build_symbol_state("BTCUSDT", closes_1m, volumes_1m, closes_5m, volumes_5m)

        self.assertEqual(state["strategy_signal"], "LONG")
        self.assertEqual(state["strategy_signal_source"], "reactive_reversion")
        self.assertEqual(state["strategy_id"], "reactive_reversion_v1")
        self.assertGreater(state["strategy_signal_score"], 0.0)
        self.assertEqual(state["trigger_direction"], "DROP_REVERSION")

    def test_build_symbol_state_blocks_reactive_signal_in_strong_trend(self) -> None:
        closes_1m = [100.0] * 27 + [102.5, 103.5, 104.0]
        volumes_1m = [1000.0] * 27 + [1800.0, 2200.0, 2600.0]
        closes_5m = [100.0 + (i * 0.4) for i in range(30)]
        volumes_5m = [5000.0] * len(closes_5m)

        with patch("tools.multi5.multi5_symbol_scanner._resolve_time_window", return_value="ACTIVE"):
            state = build_symbol_state("BTCUSDT", closes_1m, volumes_1m, closes_5m, volumes_5m)

        self.assertEqual(state["strategy_signal"], "HOLD")
        self.assertEqual(state["time_window_mode"], "ACTIVE")

    def test_collect_signal_target_symbols_includes_candidates_active_and_open(self) -> None:
        targets = collect_signal_target_symbols(
            [
                {"symbol": "QUICKUSDT"},
                {"symbol": "VOXELUSDT"},
            ],
            active_symbols={"DOGEUSDT", "QUICKUSDT"},
            open_position_symbols={"DOGEUSDT"},
            selected_symbol="BCHUSDT",
        )

        self.assertEqual(targets, {"DOGEUSDT", "QUICKUSDT", "VOXELUSDT", "BCHUSDT"})

    def test_recover_missing_position_workers_launches_for_open_positions_without_workers(self) -> None:
        launches: list[dict[str, object]] = []
        writes: list[Path] = []
        now = datetime.now(timezone.utc)

        def fake_write_json(path: Path, payload: dict) -> None:
            writes.append(path)

        def fake_run_engine(
            symbol: str,
            session_hours: float,
            max_positions: int,
            *,
            strategy_unit: str,
            strategy_signal_path_value: Path,
            take_profit_pct: float,
            stop_loss_pct: float,
        ) -> None:
            launches.append(
                {
                    "symbol": symbol,
                    "session_hours": session_hours,
                    "max_positions": max_positions,
                    "strategy_unit": strategy_unit,
                    "strategy_signal_path": strategy_signal_path_value,
                    "take_profit_pct": take_profit_pct,
                    "stop_loss_pct": stop_loss_pct,
                }
            )

        with patch("tools.multi5.run_multi5_engine.write_json", fake_write_json), patch(
            "tools.multi5.run_multi5_engine.run_engine",
            fake_run_engine,
        ):
            launched_symbols, launched_strategy_units = recover_missing_position_workers(
                open_position_symbols={"ETHUSDT", "DOGEUSDT"},
                worker_symbols={"DOGEUSDT"},
                state_by_symbol={
                    "ETHUSDT": {
                        "symbol": "ETHUSDT",
                        "strategy_id": "momentum_intraday_v1",
                        "strategy_unit": "BALANCED_INTRADAY_MOMENTUM",
                        "strategy_signal": "SHORT",
                        "strategy_signal_score": 0.71,
                        "edge_score": 1.33,
                        "take_profit_pct": 0.02,
                        "stop_loss_pct": 0.01,
                    }
                },
                engine_session_hours=2.0,
                max_position_per_symbol=1,
                launch_cooldown_sec=120,
                last_launch_at={"DOGEUSDT": now},
            )

        self.assertEqual(launched_symbols, ["ETHUSDT"])
        self.assertEqual(launched_strategy_units, ["momentum_intraday_v1"])
        self.assertEqual(len(launches), 1)
        self.assertEqual(launches[0]["symbol"], "ETHUSDT")
        self.assertEqual(launches[0]["strategy_unit"], "BALANCED_INTRADAY_MOMENTUM")
        self.assertEqual(len(writes), 1)

    def test_trade_outcome_payload_preserves_raw_pnl_precision(self) -> None:
        normalized = _normalize_trade_outcome_payload(
            {
                "symbol": "DOGEUSDT",
                "entry_price": 1.123456789,
                "exit_price": 1.223456789,
                "pnl": 0.1234567891234,
                "hold_time": 12.34567,
                "entry_quality_score": 0.987654321,
            }
        )

        self.assertEqual(normalized["entry_price"], 1.123457)
        self.assertEqual(normalized["exit_price"], 1.223457)
        self.assertEqual(normalized["pnl"], 0.123456789123)
        self.assertEqual(normalized["pnl_display"], 0.123457)
        self.assertEqual(normalized["hold_time"], 12.346)
        self.assertEqual(normalized["entry_quality_score"], 0.987654)

    def test_build_allocation_top_from_snapshot_uses_weight_order(self) -> None:
        top = build_allocation_top_from_snapshot(
            {
                "weights": {"B": 0.2, "A": 0.4, "C": 0.1},
                "raw_scores": {"A": 0.7, "B": 0.5, "C": 0.2},
            },
            limit=2,
        )

        self.assertEqual(
            top,
            [
                {"symbol": "A", "weight": 0.4, "score": 0.7},
                {"symbol": "B", "weight": 0.2, "score": 0.5},
            ],
        )

    def test_normalize_allocations_preserves_min_weight_when_feasible(self) -> None:
        weights = normalize_allocations(
            {
                "DOGEUSDT": 0.90,
                "ETHUSDT": 0.70,
                "XRPUSDT": 0.60,
                "BTCUSDT": 0.20,
                "QUICKUSDT": 1.00,
            },
            min_weight=0.05,
            max_weight=0.40,
        )

        self.assertEqual(
            set(weights),
            {"DOGEUSDT", "ETHUSDT", "XRPUSDT", "BTCUSDT", "QUICKUSDT"},
        )
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=9)
        self.assertGreaterEqual(min(weights.values()), 0.05)
        self.assertLessEqual(max(weights.values()), 0.40)

    def test_normalize_allocations_relaxes_min_weight_only_when_infeasible(self) -> None:
        scores = {f"SYM{i}": 1.0 for i in range(30)}
        weights = normalize_allocations(scores, min_weight=0.05, max_weight=0.40)

        self.assertEqual(len(weights), 30)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=9)
        expected = 1.0 / 30.0
        for weight in weights.values():
            self.assertAlmostEqual(weight, expected, places=9)

    def test_observe_portfolio_allocation_scopes_to_active_and_selected_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = RunnerConfig(
                symbol="DOGEUSDT",
                evidence_path=str(tmp / "events.jsonl"),
                summary_path=str(tmp / "summary.json"),
                runtime_health_summary_path=str(tmp / "runtime_health_summary.json"),
                portfolio_snapshot_path=str(tmp / "portfolio_metrics_snapshot.json"),
                trade_outcomes_path=str(tmp / "trade_outcomes.json"),
                strategy_performance_path=str(tmp / "strategy_performance.json"),
                global_risk_monitor_path=str(tmp / "global_risk_monitor.json"),
                market_regime_path=str(tmp / "market_regime.json"),
                portfolio_allocation_path=str(tmp / "portfolio_allocation.json"),
                strategy_signal_path=str(tmp / "strategy_signal.json"),
            )

            with patch.object(ProfitMaxV1Runner, "_seed_market_history", lambda self: None):
                runner = ProfitMaxV1Runner(config)

            with patch.object(
                runner,
                "_load_strategy_performance",
                lambda: {
                    "DOGEUSDT": {"trades": 5, "pnl": 0.5, "wins": 3, "losses": 2},
                    "ETHUSDT": {"trades": 6, "pnl": 0.9, "wins": 4, "losses": 2},
                    "XRPUSDT": {"trades": 3, "pnl": 0.2, "wins": 2, "losses": 1},
                    "BTCUSDT": {"trades": 2, "pnl": -0.3, "wins": 0, "losses": 2},
                    "UNUSEDUSDT": {"trades": 10, "pnl": 5.0, "wins": 9, "losses": 1},
                },
            ), patch.object(
                runner,
                "_latest_runtime_context",
                lambda: {
                    "active_symbol_count": 3,
                    "max_open_positions": 5,
                    "active_symbols": ["DOGEUSDT", "ETHUSDT", "XRPUSDT"],
                    "selected_symbols_batch": ["BTCUSDT", "DOGEUSDT", "ETHUSDT", "XRPUSDT"],
                },
            ), patch.object(
                runner,
                "_log_event",
                lambda *args, **kwargs: None,
            ), patch.object(
                runner,
                "_write_portfolio_allocation_snapshot",
                lambda payload: None,
            ):
                snapshot = runner._observe_portfolio_allocation(
                    portfolio_metrics={"max_drawdown": 1.5},
                    trace_id="test-trace",
                )

            self.assertIsNotNone(snapshot)
            self.assertEqual(
                snapshot["target_symbols"],
                ["DOGEUSDT", "ETHUSDT", "XRPUSDT", "BTCUSDT"],
            )
            self.assertEqual(
                snapshot["requested_target_symbols"],
                ["DOGEUSDT", "ETHUSDT", "XRPUSDT", "BTCUSDT"],
            )
            self.assertEqual(
                set(snapshot["weights"]),
                {"DOGEUSDT", "ETHUSDT", "XRPUSDT", "BTCUSDT"},
            )
            self.assertNotIn("UNUSEDUSDT", snapshot["weights"])
            self.assertAlmostEqual(snapshot["weight_sum"], 1.0, places=6)

    def test_observe_portfolio_allocation_excludes_requested_symbols_without_performance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = RunnerConfig(
                symbol="DOGEUSDT",
                evidence_path=str(tmp / "events.jsonl"),
                summary_path=str(tmp / "summary.json"),
                runtime_health_summary_path=str(tmp / "runtime_health_summary.json"),
                portfolio_snapshot_path=str(tmp / "portfolio_metrics_snapshot.json"),
                trade_outcomes_path=str(tmp / "trade_outcomes.json"),
                strategy_performance_path=str(tmp / "strategy_performance.json"),
                global_risk_monitor_path=str(tmp / "global_risk_monitor.json"),
                market_regime_path=str(tmp / "market_regime.json"),
                portfolio_allocation_path=str(tmp / "portfolio_allocation.json"),
                strategy_signal_path=str(tmp / "strategy_signal.json"),
            )

            with patch.object(ProfitMaxV1Runner, "_seed_market_history", lambda self: None):
                runner = ProfitMaxV1Runner(config)

            with patch.object(
                runner,
                "_load_strategy_performance",
                lambda: {
                    "DOGEUSDT": {"trades": 5, "pnl": 0.5, "wins": 3, "losses": 2},
                    "ETHUSDT": {"trades": 6, "pnl": 0.9, "wins": 4, "losses": 2},
                },
            ), patch.object(
                runner,
                "_latest_runtime_context",
                lambda: {
                    "active_symbols": ["DOGEUSDT"],
                    "selected_symbols_batch": ["DOGEUSDT", "ETHUSDT", "MYROUSDT"],
                },
            ), patch.object(
                runner,
                "_log_event",
                lambda *args, **kwargs: None,
            ), patch.object(
                runner,
                "_write_portfolio_allocation_snapshot",
                lambda payload: None,
            ):
                snapshot = runner._observe_portfolio_allocation(
                    portfolio_metrics={"max_drawdown": 1.5},
                    trace_id="test-trace",
                )

            self.assertEqual(snapshot["requested_target_symbol_count"], 3)
            self.assertEqual(snapshot["target_symbol_count"], 2)
            self.assertEqual(snapshot["requested_target_symbols"], ["DOGEUSDT", "ETHUSDT", "MYROUSDT"])
            self.assertEqual(snapshot["target_symbols"], ["DOGEUSDT", "ETHUSDT"])

    def test_recent_entry_side_counts_can_be_scoped_to_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = RunnerConfig(
                symbol="DOGEUSDT",
                evidence_path=str(tmp / "events.jsonl"),
                summary_path=str(tmp / "summary.json"),
                runtime_health_summary_path=str(tmp / "runtime_health_summary.json"),
                portfolio_snapshot_path=str(tmp / "portfolio_metrics_snapshot.json"),
                trade_outcomes_path=str(tmp / "trade_outcomes.json"),
                strategy_performance_path=str(tmp / "strategy_performance.json"),
                global_risk_monitor_path=str(tmp / "global_risk_monitor.json"),
                market_regime_path=str(tmp / "market_regime.json"),
                portfolio_allocation_path=str(tmp / "portfolio_allocation.json"),
                strategy_signal_path=str(tmp / "strategy_signal.json"),
            )
            with patch.object(ProfitMaxV1Runner, "_seed_market_history", lambda self: None):
                runner = ProfitMaxV1Runner(config)

            (tmp / "events.jsonl").write_text(
                "\n".join(
                    [
                        '{"event_type":"ENTRY","payload":{"symbol":"DOGEUSDT","side":"SELL"}}',
                        '{"event_type":"ENTRY","payload":{"symbol":"DOGEUSDT","side":"SELL"}}',
                        '{"event_type":"ENTRY","payload":{"symbol":"ETHUSDT","side":"BUY"}}',
                        '{"event_type":"ENTRY","payload":{"symbol":"ETHUSDT","side":"SELL"}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(runner._recent_entry_side_counts(), (1, 3))
            self.assertEqual(runner._recent_entry_side_counts(symbol="DOGEUSDT"), (0, 2))
            self.assertEqual(runner._recent_entry_side_counts(symbol="ETHUSDT"), (1, 1))

    def test_should_exit_forces_hard_timeout_even_if_profitable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = RunnerConfig(
                symbol="DOGEUSDT",
                evidence_path=str(tmp / "events.jsonl"),
                summary_path=str(tmp / "summary.json"),
                runtime_health_summary_path=str(tmp / "runtime_health_summary.json"),
                portfolio_snapshot_path=str(tmp / "portfolio_metrics_snapshot.json"),
                trade_outcomes_path=str(tmp / "trade_outcomes.json"),
                strategy_performance_path=str(tmp / "strategy_performance.json"),
                global_risk_monitor_path=str(tmp / "global_risk_monitor.json"),
                market_regime_path=str(tmp / "market_regime.json"),
                portfolio_allocation_path=str(tmp / "portfolio_allocation.json"),
                strategy_signal_path=str(tmp / "strategy_signal.json"),
                max_position_minutes=15,
            )
            with patch.object(ProfitMaxV1Runner, "_seed_market_history", lambda self: None):
                runner = ProfitMaxV1Runner(config)

            runner.position = {
                "entry_price": 100.0,
                "side": "BUY",
                "tp_pct": 0.5,
                "sl_pct": 0.5,
                "entry_ts": datetime.now(timezone.utc) - timedelta(minutes=46),
                "trace_id": "hard-timeout-test",
            }

            should_exit, reason = runner._should_exit(100.2)

            self.assertTrue(should_exit)
            self.assertEqual(reason, "timeout_exit")

    def test_write_summary_aggregates_portfolio_snapshot_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = RunnerConfig(
                symbol="DOGEUSDT",
                evidence_path=str(tmp / "events.jsonl"),
                summary_path=str(tmp / "summary.json"),
                runtime_health_summary_path=str(tmp / "runtime_health_summary.json"),
                portfolio_snapshot_path=str(tmp / "portfolio_metrics_snapshot.json"),
                trade_outcomes_path=str(tmp / "trade_outcomes.json"),
                strategy_performance_path=str(tmp / "strategy_performance.json"),
                global_risk_monitor_path=str(tmp / "global_risk_monitor.json"),
                market_regime_path=str(tmp / "market_regime.json"),
                portfolio_allocation_path=str(tmp / "portfolio_allocation.json"),
                strategy_signal_path=str(tmp / "strategy_signal.json"),
            )

            with patch.object(ProfitMaxV1Runner, "_seed_market_history", lambda self: None):
                runner = ProfitMaxV1Runner(config)

            (tmp / "portfolio_metrics_snapshot.json").write_text(
                '{"ts":"2026-03-28T17:14:06.078220+00:00","equity":10120.280464,"realized_pnl":1.786082,"total_trades":310,"portfolio_total_exposure":20.21047}',
                encoding="utf-8",
            )
            (tmp / "trade_outcomes.json").write_text(
                '[{"symbol":"DOGEUSDT","pnl":0.5},{"symbol":"ETHUSDT","pnl":1.286082}]',
                encoding="utf-8",
            )
            (tmp / "portfolio_allocation.json").write_text(
                '{"weights":{"DOGEUSDT":0.4,"ETHUSDT":0.35,"BTCUSDT":0.25},"raw_scores":{"DOGEUSDT":0.9,"ETHUSDT":0.7,"BTCUSDT":0.5},"target_symbols":["DOGEUSDT","ETHUSDT","BTCUSDT"],"target_symbol_count":3}',
                encoding="utf-8",
            )

            runner.session_realized_pnl = 0.0
            runner.daily_realized_pnl = 0.0
            runner.daily_trades = 0
            runner.peak_account_equity = 10119.0
            with patch.object(
                runner,
                "_latest_runtime_context",
                lambda: {
                    "active_symbols": ["DOGEUSDT", "ETHUSDT"],
                    "selected_symbols_batch": ["DOGEUSDT", "ETHUSDT", "BTCUSDT"],
                },
            ):
                runner._write_summary()

            summary = __import__("json").loads((tmp / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["summary_mode"], "PORTFOLIO_AGGREGATED")
            self.assertEqual(summary["symbol"], "PORTFOLIO")
            self.assertEqual(summary["writer_symbol"], "DOGEUSDT")
            self.assertEqual(summary["session_realized_pnl"], 1.786082)
            self.assertEqual(summary["daily_realized_pnl"], 1.786082)
            self.assertEqual(summary["daily_trades"], 310)
            self.assertEqual(summary["trade_outcomes_count"], 2)
            self.assertTrue(summary["position_open"])
            self.assertEqual(summary["active_symbols"], ["DOGEUSDT", "ETHUSDT"])
            self.assertEqual(summary["selected_symbols_batch"], ["DOGEUSDT", "ETHUSDT", "BTCUSDT"])
            self.assertEqual(summary["allocation_target_symbol_count"], 3)
            self.assertEqual(summary["allocation_top"][0]["symbol"], "DOGEUSDT")
            health = __import__("json").loads((tmp / "runtime_health_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(health["summary_mode"], "PORTFOLIO_AGGREGATED")
            self.assertTrue(health["engine_alive"])
            self.assertEqual(health["writer_symbol"], "DOGEUSDT")
            self.assertEqual(health["realized_pnl"], 1.786082)
            self.assertEqual(health["trade_outcomes_count"], 2)
            self.assertEqual(health["top_allocation_symbol"], "DOGEUSDT")

    def test_write_portfolio_allocation_snapshot_syncs_summary_and_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config = RunnerConfig(
                symbol="QUICKUSDT",
                evidence_path=str(tmp / "events.jsonl"),
                summary_path=str(tmp / "summary.json"),
                runtime_health_summary_path=str(tmp / "runtime_health_summary.json"),
                portfolio_snapshot_path=str(tmp / "portfolio_metrics_snapshot.json"),
                trade_outcomes_path=str(tmp / "trade_outcomes.json"),
                strategy_performance_path=str(tmp / "strategy_performance.json"),
                global_risk_monitor_path=str(tmp / "global_risk_monitor.json"),
                market_regime_path=str(tmp / "market_regime.json"),
                portfolio_allocation_path=str(tmp / "portfolio_allocation.json"),
                strategy_signal_path=str(tmp / "strategy_signal.json"),
            )

            with patch.object(ProfitMaxV1Runner, "_seed_market_history", lambda self: None):
                runner = ProfitMaxV1Runner(config)

            (tmp / "summary.json").write_text(
                '{"allocation_top":[{"symbol":"OLD","weight":0.9,"score":0.9}],"allocation_target_symbols":["OLD"],"allocation_target_symbol_count":1}',
                encoding="utf-8",
            )
            (tmp / "runtime_health_summary.json").write_text(
                '{"top_allocation_symbol":"OLD","top_allocation_weight":0.9,"allocation_target_symbol_count":1}',
                encoding="utf-8",
            )

            runner._write_portfolio_allocation_snapshot(
                {
                    "weights": {"QUICKUSDT": 0.4, "BCHUSDT": 0.35, "XRPUSDT": 0.25},
                    "raw_scores": {"QUICKUSDT": 0.7, "BCHUSDT": 0.5, "XRPUSDT": 0.3},
                    "target_symbols": ["QUICKUSDT", "BCHUSDT", "XRPUSDT"],
                    "target_symbol_count": 3,
                }
            )

            summary = __import__("json").loads((tmp / "summary.json").read_text(encoding="utf-8"))
            health = __import__("json").loads((tmp / "runtime_health_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["allocation_top"][0]["symbol"], "QUICKUSDT")
            self.assertEqual(summary["allocation_target_symbols"], ["QUICKUSDT", "BCHUSDT", "XRPUSDT"])
            self.assertEqual(summary["allocation_target_symbol_count"], 3)
            self.assertEqual(health["top_allocation_symbol"], "QUICKUSDT")
            self.assertEqual(health["top_allocation_weight"], 0.4)
            self.assertEqual(health["allocation_target_symbol_count"], 3)

    def test_main_loop_writes_portfolio_snapshot_before_summary(self) -> None:
        script = (ROOT / "tools" / "ops" / "profitmax_v1_runner.py").read_text(encoding="utf-8")
        snapshot_idx = script.find("self._maybe_write_portfolio_snapshot()")
        summary_idx = script.find("self._write_summary()", snapshot_idx)

        self.assertGreaterEqual(snapshot_idx, 0)
        self.assertGreaterEqual(summary_idx, 0)
        self.assertLess(snapshot_idx, summary_idx)

    def test_recent_short_guard_uses_effective_limit_in_testnet_profile(self) -> None:
        script = (ROOT / "tools" / "ops" / "profitmax_v1_runner.py").read_text(encoding="utf-8")

        self.assertIn("effective_recent_short_limit", script)
        self.assertIn("PROFILE_TESTNET_INTRADAY_SCALP", script)
        self.assertIn("effective_recent_short_limit += 2", script)
        self.assertIn('runtime_context.get("max_open_positions"', script)

    def test_current_bar_key_uses_primary_bar_sec(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            common_kwargs = dict(
                evidence_path=str(tmp / "events.jsonl"),
                summary_path=str(tmp / "summary.json"),
                runtime_health_summary_path=str(tmp / "runtime_health_summary.json"),
                portfolio_snapshot_path=str(tmp / "portfolio_metrics_snapshot.json"),
                trade_outcomes_path=str(tmp / "trade_outcomes.json"),
                strategy_performance_path=str(tmp / "strategy_performance.json"),
                global_risk_monitor_path=str(tmp / "global_risk_monitor.json"),
                market_regime_path=str(tmp / "market_regime.json"),
                portfolio_allocation_path=str(tmp / "portfolio_allocation.json"),
                strategy_signal_path=str(tmp / "strategy_signal.json"),
            )
            with patch.object(ProfitMaxV1Runner, "_seed_market_history", lambda self: None):
                runner_60 = ProfitMaxV1Runner(RunnerConfig(symbol="DOGEUSDT", primary_bar_sec=60, **common_kwargs))
                runner_300 = ProfitMaxV1Runner(RunnerConfig(symbol="DOGEUSDT", primary_bar_sec=300, **common_kwargs))

            fake_now = datetime(2026, 3, 29, 9, 4, 59, tzinfo=timezone(timedelta(hours=9)))
            with patch.object(profitmax_runner_module, "kst_now", return_value=fake_now):
                key_60 = runner_60._current_bar_key()
                key_300 = runner_300._current_bar_key()

            self.assertEqual(key_60, "2026-03-29-0544")
            self.assertEqual(key_300, "2026-03-29-0108")

    def test_build_arg_parser_supports_primary_bar_sec(self) -> None:
        parser = profitmax_runner_module.build_arg_parser()
        args = parser.parse_args(["--primary-bar-sec", "60"])

        self.assertEqual(args.primary_bar_sec, 60)

    def test_collect_strategy_tuning_dataset_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            runtime_dir = tmp / "logs" / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            (runtime_dir / "profitmax_v1_events.jsonl").write_text(
                "\n".join(
                    [
                        '{"ts":"2026-03-28T18:00:00Z","event_type":"REALIZED_PNL","symbol":"DOGEUSDT","payload":{"pnl":0.5}}',
                        '{"ts":"2026-03-28T18:00:01Z","event_type":"EXIT","symbol":"DOGEUSDT","payload":{"reason":"fixed_tp"}}',
                    ]
                ),
                encoding="utf-8",
            )
            (runtime_dir / "trade_outcomes.json").write_text('[{"symbol":"DOGEUSDT","pnl":0.5}]', encoding="utf-8")
            (runtime_dir / "strategy_performance.json").write_text('{"DOGEUSDT":{"trades":1}}', encoding="utf-8")

            script_path = ROOT / "tools" / "ops" / "collect_strategy_tuning_dataset.py"
            proc = subprocess.run(
                [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(script_path)],
                cwd=tmp,
                capture_output=True,
                text=True,
                env={**__import__("os").environ, "NT_PROJECT_ROOT": str(tmp)},
                check=False,
            )

            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            out_path = runtime_dir / "strategy_tuning_dataset.json"
            self.assertTrue(out_path.exists())
            payload = __import__("json").loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["trade_outcomes_count"], 1)
            self.assertEqual(payload["exit_reason_counts"]["fixed_tp"], 1)


if __name__ == "__main__":
    unittest.main()
