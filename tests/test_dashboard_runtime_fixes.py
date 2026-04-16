from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.dashboard import multi5_dashboard_server as dashboard_server  # noqa: E402


class DashboardRuntimeFixTests(unittest.TestCase):
    def test_build_equity_history_filters_non_positive_points(self) -> None:
        dashboard_server._EQUITY_HISTORY_CACHE["ts"] = 0.0
        dashboard_server._EQUITY_HISTORY_CACHE["data"] = []

        with patch.object(
            dashboard_server,
            "tail_jsonl_rows",
            lambda path, limit=400: [
                {"ts": "2026-03-28T16:55:43.478505+00:00", "payload": {"account_equity": 0.0}},
                {"ts": "2026-03-28T16:55:44.478505+00:00", "payload": {"account_equity": -10.0}},
                {"ts": "2026-03-28T16:55:45.478505+00:00", "payload": {"account_equity": 10120.5}},
                {"ts": "2026-03-28T16:55:45.478505+00:00", "payload": {"account_equity": 10120.5}},
                {"ts": "2026-03-28T16:55:46.478505+00:00", "payload": {"account_equity": 10121.0}},
            ],
        ):
            points = dashboard_server.build_equity_history(limit=1000, window_minutes=60 * 24 * 365)

        self.assertEqual(
            points,
            [
                {"ts": "2026-03-28T16:55:45.478505+00:00", "equity": 10120.5},
                {"ts": "2026-03-28T16:55:46.478505+00:00", "equity": 10121.0},
            ],
        )

    def test_restart_engine_script_stops_guards_before_starting_engine(self) -> None:
        script = (ROOT / "BOOT" / "restart_engine.ps1").read_text(encoding="utf-8")

        self.assertIn("phase5_autoguard", script)
        self.assertIn("runtime_guard", script)
        self.assertIn("multi5_dashboard_server", script)
        self.assertIn("prune_stale_worker_locks", script)
        self.assertIn("post_reboot_status_probe", script)
        self.assertIn("validate_runtime_health_summary", script)
        self.assertIn("Wait-ForPortListening", script)
        self.assertIn("Wait-ForFreshFile", script)
        self.assertIn("ENGINE_RESTART_HEALTH_VALIDATION=STALE", script)
        self.assertIn("ENGINE_RESTART_POST_REBOOT_PROBE=STALE", script)
        self.assertIn("Stop-RestartTargets", script)
        self.assertIn("Wait-UntilStopped", script)
        self.assertIn("& $startEngineScript", script)
        self.assertIn("& $startRuntimeGuardScript", script)
        self.assertIn("& $startAutoguardScript", script)

    def test_runtime_payload_prefers_portfolio_snapshot_for_realized_pnl(self) -> None:
        dashboard_server._EQUITY_HISTORY_CACHE["ts"] = 0.0
        dashboard_server._EQUITY_HISTORY_CACHE["data"] = []

        def fake_load_json(path: Path) -> dict:
            name = path.name
            if name == "profitmax_v1_summary.json":
                return {
                    "session_realized_pnl": 0.0,
                    "daily_realized_pnl": 0.0,
                    "daily_trades": 0,
                    "ts": "2026-03-28T17:14:06.078220+00:00",
                }
            if name == "portfolio_metrics_snapshot.json":
                return {
                    "ts": "2026-03-28T17:14:06.078220+00:00",
                    "equity": 10120.280464,
                    "realized_pnl": 1.786082,
                    "total_trades": 310,
                    "portfolio_total_exposure": 0.0,
                    "unrealized_pnl": 0.0,
                    "drawdown": 6.901005,
                    "win_rate": 0.425806,
                }
            return {}

        with patch.object(
            dashboard_server,
            "tail_jsonl",
            side_effect=[
                {
                    "ts": "2026-03-28T17:14:55.804117+00:00",
                    "engine_running": True,
                    "active_symbols": ["DOGEUSDT"],
                    "selected_symbol": "DOGEUSDT",
                    "selected_symbols_batch": ["DOGEUSDT"],
                },
                {"ts": "2026-03-28T17:14:29.443629+00:00"},
            ],
        ), patch.object(
            dashboard_server,
            "load_json",
            side_effect=fake_load_json,
        ), patch.object(
            dashboard_server,
            "classify_runtime_processes",
            lambda: {"effective_role_count": 0, "raw_process_count": 0, "roles": []},
        ), patch.object(
            dashboard_server,
            "latest_dashboard_snapshot",
            lambda: {},
        ), patch.object(
            dashboard_server,
            "latest_honey_report_dir",
            lambda: None,
        ), patch.object(
            dashboard_server,
            "load_env_file",
            lambda path: {},
        ), patch.object(
            dashboard_server,
            "fetch_local_json",
            lambda url: {},
        ), patch.object(
            dashboard_server,
            "build_equity_history",
            lambda: [{"ts": "2026-03-28T17:14:06.078220+00:00", "equity": 10120.280464}],
        ), patch.object(
            dashboard_server,
            "build_allocation_top",
            lambda limit=8: [],
        ):
            payload = dashboard_server.build_runtime_payload()

        self.assertEqual(payload["session_realized_pnl"], "1.786082")
        self.assertEqual(payload["daily_realized_pnl"], "1.786082")
        self.assertEqual(payload["runtime_session_realized_pnl"], "1.786082")
        self.assertEqual(payload["kst_daily_trade_count"], 310)
        self.assertEqual(payload["selected_symbol_count"], 1)

    def test_runtime_payload_uses_engine_process_role_when_runtime_flag_is_false(self) -> None:
        dashboard_server._EQUITY_HISTORY_CACHE["ts"] = 0.0
        dashboard_server._EQUITY_HISTORY_CACHE["data"] = []

        with patch.object(
            dashboard_server,
            "tail_jsonl",
            side_effect=[
                {
                    "ts": "2026-03-28T17:14:55.804117+00:00",
                    "engine_running": False,
                    "active_symbols": [],
                    "selected_symbol": "DOGEUSDT",
                    "selected_symbols_batch": ["DOGEUSDT"],
                },
                {"ts": "2026-03-28T17:14:29.443629+00:00"},
            ],
        ), patch.object(
            dashboard_server,
            "load_json",
            side_effect=lambda path: {
                "ts": "2026-03-28T17:14:06.078220+00:00",
                "equity": 10120.280464,
                "realized_pnl": 1.786082,
                "total_trades": 310,
                "portfolio_total_exposure": 0.0,
                "unrealized_pnl": 0.0,
                "drawdown": 6.901005,
                "win_rate": 0.425806,
            } if path.name == "portfolio_metrics_snapshot.json" else {},
        ), patch.object(
            dashboard_server,
            "classify_runtime_processes",
            lambda: {
                "effective_role_count": 1,
                "raw_process_count": 2,
                "roles": [{"role": "engine", "label": "multi5_engine", "root_pid": 1234, "pid_count": 2, "pids": [1234, 1235]}],
            },
        ), patch.object(
            dashboard_server,
            "latest_dashboard_snapshot",
            lambda: {},
        ), patch.object(
            dashboard_server,
            "latest_honey_report_dir",
            lambda: None,
        ), patch.object(
            dashboard_server,
            "load_env_file",
            lambda path: {},
        ), patch.object(
            dashboard_server,
            "fetch_local_json",
            lambda url: {},
        ), patch.object(
            dashboard_server,
            "build_equity_history",
            lambda: [{"ts": "2026-03-28T17:14:06.078220+00:00", "equity": 10120.280464}],
        ), patch.object(
            dashboard_server,
            "build_allocation_top",
            lambda limit=8: [],
        ):
            payload = dashboard_server.build_runtime_payload()

        self.assertEqual(payload["engine_status"], "RUNNING")
        self.assertEqual(payload["engine_alive"], "true")
        self.assertEqual(payload["runtime_alive"], "true")

    def test_phase5_autoguard_has_health_restart_policy(self) -> None:
        script = (ROOT / "BOOT" / "phase5_autoguard.ps1").read_text(encoding="utf-8")

        self.assertIn("HealthRestartCooldownSec", script)
        self.assertIn("WarnRestartThreshold", script)
        self.assertIn("Apply-RuntimeHealthPolicy", script)
        self.assertIn("Invoke-HealthDrivenRestart", script)
        self.assertIn("Get-HealthActionClass", script)
        self.assertIn("$script:ImmediateRestartIssues", script)
        self.assertIn("$script:SoftFailIssues", script)
        self.assertIn("$script:NoRestartIssues", script)
        self.assertIn("$restartEngineScript", script)
        self.assertIn("HEALTH_RESTART_TRIGGER", script)
        self.assertIn("WarmWorkerTargetCount", script)
        self.assertIn("Get-LatestSelectedSymbols", script)
        self.assertIn('role=$workerRole', script)

    def test_validate_runtime_health_summary_emits_action_class(self) -> None:
        script = (ROOT / "BOOT" / "validate_runtime_health_summary.ps1").read_text(encoding="utf-8")

        self.assertIn("Get-HealthActionClass", script)
        self.assertIn("action_class", script)
        self.assertIn("restart_immediate", script)
        self.assertIn("restart_soft", script)
        self.assertIn("no_restart", script)

    def test_post_reboot_probe_uses_root_process_count(self) -> None:
        script = (ROOT / "BOOT" / "post_reboot_status_probe.ps1").read_text(encoding="utf-8")

        self.assertIn("Get-RootProcCount", script)
        self.assertIn('engine_root_count = Get-RootProcCount "run_multi5_engine.py"', script)
        self.assertIn('worker_count = Get-RootProcCount "profitmax_v1_runner.py"', script)
        self.assertIn('dashboard_count = Get-RootProcCount "multi5_dashboard_server.py"', script)

    def test_reset_runtime_data_script_clears_runtime_service_and_reports(self) -> None:
        script = (ROOT / "BOOT" / "reset_runtime_data.ps1").read_text(encoding="utf-8")

        self.assertIn("logs\\runtime", script)
        self.assertIn("logs\\service", script)
        self.assertIn("reports", script)
        self.assertIn("STATE_RESET=YES", script)
        self.assertIn("profitmax_v1_runner", script)

    def test_start_project_uses_safe_boot_scripts(self) -> None:
        script = (ROOT / "scripts" / "start_project.ps1").read_text(encoding="utf-8")

        self.assertIn("start_api_8100_safe.ps1", script)
        self.assertIn("start_dashboard_8788.ps1", script)
        self.assertIn("Invoke-BootScript", script)
        self.assertIn("Boot output:", script)

    def test_start_engine_stops_stale_workers_before_new_boot(self) -> None:
        script = (ROOT / "BOOT" / "start_engine.ps1").read_text(encoding="utf-8")

        self.assertIn("Get-WorkerProcesses", script)
        self.assertIn("Stop-StaleWorkers", script)
        self.assertIn("STALE_WORKER_STOPPED_PID", script)


if __name__ == "__main__":
    unittest.main()
