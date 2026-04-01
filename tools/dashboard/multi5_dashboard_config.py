from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_ROOT / "logs" / "runtime"

SCAN_LOG_PATH = RUNTIME_DIR / "multi5_symbol_scan.jsonl"
EVENT_LOG_PATH = RUNTIME_DIR / "profitmax_v1_events.jsonl"
DAILY_PNL_PATH = RUNTIME_DIR / "daily_pnl_report.txt"

HOST = "127.0.0.1"
PORT = 8788
REFRESH_INTERVAL_SEC = 1
