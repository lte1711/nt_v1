#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen
import time
import os


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_LOG = ROOT / "logs" / "runtime" / "multi5_runtime_events.jsonl"
SUMMARY_LOG = ROOT / "logs" / "runtime" / "profitmax_v1_summary.json"
EVENTS_LOG = ROOT / "logs" / "runtime" / "profitmax_v1_events.jsonl"
HTML_PATH = ROOT / "tools" / "dashboard" / "multi5_dashboard.html"
REPORTS_ROOT = ROOT / "reports"
_SNAPSHOT_CACHE: dict[str, Any] = {"ts": 0.0, "data": {}}
_HONEY_DIR_CACHE: dict[str, Any] = {"ts": 0.0, "path": None}
_EQUITY_HISTORY_CACHE: dict[str, Any] = {"ts": 0.0, "data": []}
_PROCESS_ROLE_CACHE: dict[str, Any] = {"ts": 0.0, "data": {"roles": [], "effective_role_count": 0, "raw_process_count": 0}}
_KST_DAILY_SYMBOL_CACHE: dict[str, Any] = {"ts": 0.0, "data": {"summary": {}, "rows": []}}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def latest_ts_text(*values: Any) -> str:
    latest_dt: datetime | None = None
    latest_text = "-"
    for value in values:
        dt = parse_iso_ts(value)
        if dt is None:
            continue
        if latest_dt is None or dt > latest_dt:
            latest_dt = dt
            latest_text = str(value)
    return latest_text


def parse_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return default


def describe_equity_source(source: str) -> str:
    mapping = {
        "portfolio_metrics_snapshot": "최신 포트폴리오 스냅샷",
        "worker_event_account_equity": "워커 이벤트 실계좌 자산",
        "stale_portfolio_metrics_snapshot": "오래된 포트폴리오 스냅샷",
        "summary_peak_fallback": "요약 파일 최대 자산값 보정",
        "none": "사용 가능한 자산 소스 없음",
    }
    return mapping.get(source, source or "-")


def describe_equity_source(source: str) -> str:
    # Override the earlier corrupted string table with stable ASCII labels.
    mapping = {
        "portfolio_metrics_snapshot": "Latest portfolio metrics snapshot",
        "worker_event_account_equity": "Worker event account equity",
        "stale_portfolio_metrics_snapshot": "Stale portfolio metrics snapshot",
        "summary_peak_fallback": "Summary peak equity fallback",
        "none": "No equity source available",
    }
    return mapping.get(source, source or "-")


def tail_jsonl(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            end = f.tell()
            block = 4096
            data = b""
            while end > 0 and b"\n" not in data:
                size = min(block, end)
                end -= size
                f.seek(end)
                data = f.read(size) + data
            lines = [line.strip() for line in data.decode("utf-8", errors="ignore").splitlines() if line.strip()]
            if not lines:
                return None
            return json.loads(lines[-1])
    except Exception:
        return None


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_text(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None


def tail_jsonl_rows(path: Path, limit: int = 400) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            end = f.tell()
            block = 65536
            data = b""
            line_count = 0
            while end > 0 and line_count <= limit + 1:
                size = min(block, end)
                end -= size
                f.seek(end)
                data = f.read(size) + data
                line_count = data.count(b"\n")
            rows: list[dict[str, Any]] = []
            for line in data.decode("utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    rows.append(parsed)
            return rows[-limit:]
    except Exception:
        return []


def build_equity_history(limit: int = 1000, window_minutes: int = 60) -> list[dict[str, Any]]:
    now = time.time()
    if now - float(_EQUITY_HISTORY_CACHE.get("ts", 0.0)) < 10:
        return list(_EQUITY_HISTORY_CACHE.get("data", []))

    # Event volume can be high enough that a small tail only covers a few minutes.
    # This range is wide enough to cover the recent hour in current runtime density
    # without stalling the dashboard on every refresh.
    rows = tail_jsonl_rows(EVENTS_LOG, 35000)
    points: list[dict[str, Any]] = []
    cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=max(1, window_minutes))
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        equity = payload.get("account_equity")
        if equity in (None, "", "-"):
            continue
        try:
            equity_value = float(equity)
        except Exception:
            continue
        if equity_value <= 0.0:
            continue
        ts_value = str(row.get("ts") or "").strip()
        if not ts_value:
            continue
        ts_dt = parse_iso_ts(ts_value)
        if ts_dt is None or ts_dt < cutoff_dt:
            continue
        points.append({"ts": ts_value, "equity": round(equity_value, 6)})
    if not points:
        return []
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for point in sorted(points, key=lambda item: item["ts"]):
        key = f"{point['ts']}|{point['equity']}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(point)
    if len(deduped) <= limit:
        _EQUITY_HISTORY_CACHE["ts"] = now
        _EQUITY_HISTORY_CACHE["data"] = deduped
        return deduped
    result = deduped[-limit:]
    _EQUITY_HISTORY_CACHE["ts"] = now
    _EQUITY_HISTORY_CACHE["data"] = result
    return result


def build_allocation_top(limit: int = 8) -> list[dict[str, Any]]:
    allocation = load_json(ROOT / "logs" / "runtime" / "portfolio_allocation.json") or {}
    weights = allocation.get("weights")
    raw_scores = allocation.get("raw_scores")
    if not isinstance(weights, dict):
        return []
    rows: list[dict[str, Any]] = []
    for symbol, weight in weights.items():
        try:
            weight_value = float(weight)
        except Exception:
            continue
        score_value = 0.0
        if isinstance(raw_scores, dict):
            try:
                score_value = float(raw_scores.get(symbol, 0.0) or 0.0)
            except Exception:
                score_value = 0.0
        rows.append(
            {
                "symbol": str(symbol),
                "weight": round(weight_value, 6),
                "score": round(score_value, 6),
            }
        )
    rows.sort(key=lambda item: (item["weight"], item["score"]), reverse=True)
    return rows[:limit]


def build_kst_daily_symbol_stats(limit: int = 12) -> dict[str, Any]:
    now = time.time()
    cached = _KST_DAILY_SYMBOL_CACHE.get("data", {})
    if now - float(_KST_DAILY_SYMBOL_CACHE.get("ts", 0.0)) < 10:
        return {
            "summary": dict(cached.get("summary", {})),
            "rows": list(cached.get("rows", [])),
        }

    try:
        from zoneinfo import ZoneInfo

        kst = ZoneInfo("Asia/Seoul")
    except Exception:
        kst = timezone(timedelta(hours=9))

    now_kst = datetime.now(kst)
    day_start_kst = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = day_start_kst.astimezone(timezone.utc)

    trade_outcomes_path = ROOT / "logs" / "runtime" / "trade_outcomes.json"
    try:
        raw_trades = json.loads(trade_outcomes_path.read_text(encoding="utf-8"))
    except Exception:
        raw_trades = []
    symbol_map: dict[str, dict[str, Any]] = {}
    total_invested = 0.0
    total_pnl = 0.0
    total_trades = 0

    for row in raw_trades if isinstance(raw_trades, list) else []:
        if not isinstance(row, dict):
            continue
        ts_dt = parse_iso_ts(row.get("timestamp"))
        if ts_dt is None or ts_dt < day_start_utc:
            continue
        symbol = str(row.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        side = str(row.get("side") or "").upper().strip()
        entry_price = parse_float(row.get("entry_price"))
        exit_price = parse_float(row.get("exit_price"))
        pnl = parse_float(row.get("pnl"))
        if entry_price <= 0.0 or exit_price <= 0.0:
            continue
        unit_pnl = 0.0
        if side == "BUY":
            unit_pnl = exit_price - entry_price
        elif side == "SELL":
            unit_pnl = entry_price - exit_price
        qty = 0.0
        if abs(unit_pnl) > 1e-12:
            qty = abs(pnl / unit_pnl)
        if qty <= 0.0:
            continue
        invested = round(abs(qty * entry_price), 6)
        total_invested += invested
        total_pnl += pnl
        total_trades += 1

        bucket = symbol_map.setdefault(
            symbol,
            {
                "symbol": symbol,
                "invested_amount": 0.0,
                "realized_pnl": 0.0,
                "trade_count": 0,
                "last_trade_ts": "-",
            },
        )
        bucket["invested_amount"] = round(float(bucket["invested_amount"]) + invested, 6)
        bucket["realized_pnl"] = round(float(bucket["realized_pnl"]) + pnl, 6)
        bucket["trade_count"] = int(bucket["trade_count"]) + 1
        bucket["last_trade_ts"] = str(row.get("timestamp") or bucket["last_trade_ts"])

    result_rows: list[dict[str, Any]] = []
    for item in symbol_map.values():
        invested_amount = parse_float(item.get("invested_amount"))
        realized_pnl = parse_float(item.get("realized_pnl"))
        return_pct = round((realized_pnl / invested_amount) * 100.0, 6) if invested_amount > 0.0 else 0.0
        result_rows.append(
            {
                **item,
                "return_pct": return_pct,
            }
        )

    result_rows.sort(
        key=lambda item: (abs(parse_float(item.get("realized_pnl"))), parse_float(item.get("invested_amount"))),
        reverse=True,
    )
    result_rows = result_rows[:limit]
    summary = {
        "day_start_kst": day_start_kst.isoformat(),
        "now_kst": now_kst.isoformat(),
        "total_invested_amount": round(total_invested, 6),
        "total_realized_pnl": round(total_pnl, 6),
        "total_trade_count": total_trades,
        "symbol_count": len(symbol_map),
    }
    result = {"summary": summary, "rows": result_rows}
    _KST_DAILY_SYMBOL_CACHE["ts"] = now
    _KST_DAILY_SYMBOL_CACHE["data"] = result
    return {"summary": dict(summary), "rows": list(result_rows)}


def classify_runtime_processes() -> dict[str, Any]:
    now = time.time()
    if now - float(_PROCESS_ROLE_CACHE.get("ts", 0.0)) < 5:
        return dict(_PROCESS_ROLE_CACHE.get("data", {}))
    try:
        import subprocess

        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine } | "
                "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress -Depth 3"
            ),
        ]
        raw = subprocess.check_output(cmd, text=True).strip()
        if not raw:
            result = {"roles": [], "effective_role_count": 0, "raw_process_count": 0}
            _PROCESS_ROLE_CACHE["ts"] = now
            _PROCESS_ROLE_CACHE["data"] = result
            return dict(result)
        data = json.loads(raw)
        rows = [data] if isinstance(data, dict) else data if isinstance(data, list) else []
    except Exception:
        result = {"roles": [], "effective_role_count": 0, "raw_process_count": 0}
        _PROCESS_ROLE_CACHE["ts"] = now
        _PROCESS_ROLE_CACHE["data"] = result
        return dict(result)

    relevant: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cmdline = str(row.get("CommandLine", ""))
        lower = cmdline.lower()
        role = None
        label = None
        if "multi5_dashboard_server.py" in lower:
            role = "dashboard"
            label = "dashboard_8787"
        elif "uvicorn next_trade.api.app:app" in lower:
            role = "api"
            label = "api_8100"
        elif "run_multi5_engine.py" in lower:
            role = "engine"
            label = "multi5_engine"
        elif "profitmax_v1_runner.py" in lower:
            role = "worker"
            symbol = "-"
            match = None
            try:
                import re
                match = re.search(r"--symbol(?:\s+|=)([A-Za-z0-9_]+)", cmdline)
            except Exception:
                match = None
            if match:
                symbol = match.group(1).upper()
            label = f"worker:{symbol}"
        if role and label:
            relevant.append(
                {
                    "pid": int(row.get("ProcessId", 0) or 0),
                    "ppid": int(row.get("ParentProcessId", 0) or 0),
                    "role": role,
                    "label": label,
                }
            )

    pid_map = {row["pid"]: row for row in relevant}
    root_rows: list[dict[str, Any]] = []
    for row in relevant:
        parent = pid_map.get(row["ppid"])
        if parent and parent["label"] == row["label"]:
            continue
        root_rows.append(row)

    root_pid_sets: dict[str, set[int]] = {}
    for row in root_rows:
        root_pid_sets.setdefault(row["label"], set()).add(int(row["pid"]))

    grouped: dict[str, dict[str, Any]] = {}
    for row in relevant:
        group = grouped.setdefault(
            row["label"],
            {
                "label": row["label"],
                "role": row["role"],
                "root_pid": row["pid"],
                "pid_count": 0,
                "pids": [],
                "root_chain_count": 0,
                "root_pids": [],
                "duplicate_independent_count": 0,
                "wrapper_child_chain_present": False,
            },
        )
        if row in root_rows:
            group["root_pid"] = row["pid"]
        group["pid_count"] += 1
        group["pids"].append(row["pid"])

    for label, group in grouped.items():
        root_pids = sorted(root_pid_sets.get(label, set()))
        root_chain_count = len(root_pids)
        pid_count = int(group.get("pid_count", 0) or 0)
        group["root_pids"] = root_pids
        group["root_chain_count"] = root_chain_count
        group["duplicate_independent_count"] = max(root_chain_count - 1, 0)
        group["wrapper_child_chain_present"] = pid_count > root_chain_count

    roles = sorted(grouped.values(), key=lambda item: (item["role"], item["label"]))
    result = {
        "roles": roles,
        "effective_role_count": len(roles),
        "raw_process_count": len(relevant),
    }
    _PROCESS_ROLE_CACHE["ts"] = now
    _PROCESS_ROLE_CACHE["data"] = result
    return dict(result)


def load_dashboard_html() -> str:
    html = load_text(HTML_PATH)
    if not html:
        raise FileNotFoundError(f"DASHBOARD_HTML_MISSING: {HTML_PATH}")
    return html


def latest_honey_report_dir() -> Path | None:
    now = time.time()
    cached_path = _HONEY_DIR_CACHE.get("path")
    if now - float(_HONEY_DIR_CACHE.get("ts", 0.0)) < 30 and cached_path:
        return cached_path
    if not REPORTS_ROOT.exists():
        return None
    report_dirs = [p for p in REPORTS_ROOT.iterdir() if p.is_dir()]
    if not report_dirs:
        return None
    report_dirs.sort(key=lambda p: p.name, reverse=True)
    for base in report_dirs:
        candidate = base / "honey_execution_reports"
        if candidate.exists():
            _HONEY_DIR_CACHE["ts"] = now
            _HONEY_DIR_CACHE["path"] = candidate
            return candidate
    return None


def latest_dashboard_snapshot() -> dict[str, Any]:
    now = time.time()
    if now - float(_SNAPSHOT_CACHE.get("ts", 0.0)) < 30:
        return dict(_SNAPSHOT_CACHE.get("data", {}))
    snapshots = sorted(
        REPORTS_ROOT.rglob("_dashboard_runtime_snapshot_latest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for snapshot_path in snapshots:
        data = load_json(snapshot_path)
        if data:
            _SNAPSHOT_CACHE["ts"] = now
            _SNAPSHOT_CACHE["data"] = data
            return data
    _SNAPSHOT_CACHE["ts"] = now
    _SNAPSHOT_CACHE["data"] = {}
    return {}


def parse_key_value_report(path: Path) -> dict[str, str]:
    raw = load_text(path)
    if not raw:
        return {}
    result: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()
    except Exception:
        return {}
    return result


def fetch_local_json(url: str, timeout: float = 3.0) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:
        return {}


def build_runtime_payload() -> dict[str, Any]:
    runtime = tail_jsonl(RUNTIME_LOG) or {}
    summary = load_json(SUMMARY_LOG) or {}
    worker_event = tail_jsonl(EVENTS_LOG) or {}
    process_info = classify_runtime_processes()
    snapshot = latest_dashboard_snapshot()
    report_dir = latest_honey_report_dir()
    auto_boot = (load_json(report_dir / "auto_boot_completion_status.json") or {}) if report_dir else {}
    phase5_status = parse_key_value_report(report_dir / "nt_phase5_multi_symbol_status.txt") if report_dir else {}
    portfolio_snapshot = load_json(ROOT / "logs" / "runtime" / "portfolio_metrics_snapshot.json") or {}
    env_map = load_env_file(ROOT / ".env")
    investor_probe = fetch_local_json("http://127.0.0.1:8100/api/investor/account")
    investor_positions_probe = fetch_local_json("http://127.0.0.1:8100/api/v1/investor/positions")
    api_status_probe = fetch_local_json("http://127.0.0.1:8100/api/status")
    kpi_source_name = "portfolio_metrics_snapshot.json"
    kpi_recomputed_from = "profitmax_v1_events.jsonl"
    equity_history = build_equity_history()
    kst_daily_symbol_stats = build_kst_daily_symbol_stats()

    active_symbols = runtime.get("active_symbols") or []
    launched_symbols = runtime.get("launched_symbols") or []
    selected_symbol = runtime.get("selected_symbol") or "-"
    runtime_ts = runtime.get("ts") or utc_now_iso()
    worker_last_ts = latest_ts_text(summary.get("ts"), worker_event.get("ts"), runtime_ts)
    runtime_dt = parse_iso_ts(runtime_ts)
    worker_dt = parse_iso_ts(worker_last_ts)
    worker_lag_sec = max(0, int((runtime_dt - worker_dt).total_seconds())) if runtime_dt and worker_dt else 0
    worker_status = "OK" if worker_lag_sec <= 30 else "WARN"
    portfolio_snapshot_ts = parse_iso_ts(portfolio_snapshot.get("ts"))
    portfolio_snapshot_age_sec = (
        max(0, int((runtime_dt - portfolio_snapshot_ts).total_seconds()))
        if runtime_dt and portfolio_snapshot_ts
        else -1
    )
    portfolio_snapshot_is_fresh = portfolio_snapshot_age_sec >= 0 and portfolio_snapshot_age_sec <= 120
    latest_equity_point = equity_history[-1] if equity_history else {}
    latest_event_equity = parse_float(latest_equity_point.get("equity"))
    snapshot_equity = parse_float(portfolio_snapshot.get("equity"))
    current_equity_source = "none"
    if snapshot_equity > 0.0 and portfolio_snapshot_is_fresh:
        current_equity_value = round(snapshot_equity, 6)
        current_equity_source = "portfolio_metrics_snapshot"
    elif latest_event_equity > 0.0:
        current_equity_value = round(latest_event_equity, 6)
        current_equity_source = "worker_event_account_equity"
    elif snapshot_equity > 0.0:
        current_equity_value = round(snapshot_equity, 6)
        current_equity_source = "stale_portfolio_metrics_snapshot"
    else:
        current_equity_value = round(parse_float(summary.get("peak_account_equity")), 6)
        current_equity_source = "summary_peak_fallback" if current_equity_value > 0.0 else "none"
    current_equity_source_label = describe_equity_source(current_equity_source)
    available_balance_value = parse_float(snapshot.get("account_available_balance"))
    if available_balance_value <= 0.0:
        available_balance_value = current_equity_value
    api_process_count = int(api_status_probe.get("process_count", 0) or 0) if isinstance(api_status_probe, dict) else 0
    api_python_process_count = int(api_status_probe.get("python_process_count", 0) or 0) if isinstance(api_status_probe, dict) else 0
    investor_positions_raw = investor_positions_probe.get("positions", []) if isinstance(investor_positions_probe, dict) else []
    investor_open_positions = []
    position_notional_exposure = 0.0
    position_unrealized_pnl = 0.0
    long_position_count = 0
    short_position_count = 0
    for row in investor_positions_raw if isinstance(investor_positions_raw, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            amt = float(row.get("positionAmt", 0.0) or 0.0)
        except Exception:
            amt = 0.0
        if abs(amt) <= 1e-12:
            continue
        try:
            entry_price = float(row.get("entryPrice", 0.0) or 0.0)
        except Exception:
            entry_price = 0.0
        try:
            position_unrealized_pnl += float(row.get("unRealizedProfit", 0.0) or 0.0)
        except Exception:
            pass
        position_notional_exposure += abs(amt) * entry_price
        if amt > 0:
            long_position_count += 1
        elif amt < 0:
            short_position_count += 1
        investor_open_positions.append(row)

    exchange_open_position_count = len(investor_open_positions)
    portfolio_total_exposure = float(
        portfolio_snapshot.get("portfolio_total_exposure", phase5_status.get("TOTAL_EXPOSURE", 0.0)) or 0.0
    )
    if portfolio_total_exposure <= 0.0 and position_notional_exposure > 0.0:
        portfolio_total_exposure = round(position_notional_exposure, 6)
    unrealized_pnl_value = float(
        portfolio_snapshot.get("unrealized_pnl", snapshot.get("unrealized_pnl_live", 0.0)) or 0.0
    )
    if investor_open_positions and abs(unrealized_pnl_value) <= 1e-12 and abs(position_unrealized_pnl) > 0.0:
        unrealized_pnl_value = round(position_unrealized_pnl, 6)
    exposure_ratio_value = portfolio_snapshot.get("exposure_ratio")
    recompute_exposure_ratio = exposure_ratio_value in (None, "", "-") or not portfolio_snapshot_is_fresh
    if not recompute_exposure_ratio:
        try:
            recompute_exposure_ratio = float(exposure_ratio_value or 0.0) <= 0.0 and portfolio_total_exposure > 0.0
        except Exception:
            recompute_exposure_ratio = True
    if recompute_exposure_ratio:
        account_equity_for_ratio = current_equity_value
        exposure_ratio_value = round(portfolio_total_exposure / account_equity_for_ratio, 6) if account_equity_for_ratio > 0 else 0.0
    realized_pnl_value = parse_float(portfolio_snapshot.get("realized_pnl", summary.get("session_realized_pnl", 0.0)))
    total_profit_value = round(realized_pnl_value + unrealized_pnl_value, 6)
    principal_capital_value = round(current_equity_value - total_profit_value, 6)
    if principal_capital_value <= 0.0:
        principal_capital_value = round(current_equity_value or parse_float(portfolio_snapshot.get("equity")) or 0.0, 6)
    invested_return_pct = round((total_profit_value / principal_capital_value) * 100.0, 6) if principal_capital_value > 0 else 0.0
    position_open = exchange_open_position_count > 0
    if position_open:
        position_symbol = ",".join(
            sorted(
                {
                    str(row.get("symbol", "")).strip()
                    for row in investor_open_positions
                    if str(row.get("symbol", "")).strip()
                }
            )
        ) or (summary.get("symbol") or "-")
    else:
        position_symbol = "-"
    testnet_api_base = (
        str(investor_probe.get("api_base") or env_map.get("BINANCE_TESTNET_BASE_URL") or env_map.get("BINANCE_FUTURES_TESTNET_BASE_URL") or "https://testnet.binancefuture.com")
    )
    credentials_present = bool(investor_probe.get("credentials_present"))
    execution_mode_env = str(env_map.get("EXECUTION_MODE") or "UNKNOWN")
    binance_testnet_enabled = str(env_map.get("BINANCE_TESTNET") or "").lower() in {"1", "true", "yes", "on"}
    api_base_is_testnet = "testnet" in testnet_api_base.lower()
    process_roles = process_info.get("roles", []) if isinstance(process_info, dict) else []
    engine_process_alive = any(str(role.get("role", "")).strip().lower() == "engine" for role in process_roles)
    effective_engine_running = bool(runtime.get("engine_running")) or engine_process_alive
    realtime_exchange_link_ok = effective_engine_running and credentials_present and api_base_is_testnet
    health_warnings: list[str] = []
    if worker_lag_sec > 30:
        health_warnings.append(f"워커 하트비트 지연 {worker_lag_sec}초")
    if api_process_count <= 0:
        health_warnings.append("API 상태에 유효 프로세스가 0개로 표시됩니다")
    if not realtime_exchange_link_ok:
        health_warnings.append("Binance 실시간 연동이 확인되지 않았습니다")
    if not effective_engine_running:
        health_warnings.append("엔진이 실행 중이 아닙니다")
    if portfolio_snapshot_age_sec > 120:
        health_warnings.append(
            f"포트폴리오 스냅샷이 {portfolio_snapshot_age_sec}초 동안 갱신되지 않았습니다. 현재 카드는 {current_equity_source_label} 기준입니다"
        )

    runtime_realized_pnl_value = portfolio_snapshot.get("realized_pnl", summary.get("daily_realized_pnl", 0))
    trade_count_value = portfolio_snapshot.get("total_trades", summary.get("daily_trades", 0))
    pnl_source_name = "portfolio_metrics_snapshot" if portfolio_snapshot.get("realized_pnl") is not None else "summary_json"

    payload = {
        "engine_status": "RUNNING" if effective_engine_running else "STOPPED",
        "current_operation_status": "LIVE_RUNTIME_ACTIVE" if effective_engine_running else "SAFE_START_RUNTIME_ACTIVE",
        "ops_health_status": "OK",
        "last_update": runtime_ts,
        "runtime_alive": "true" if effective_engine_running else "false",
        "engine_alive": "true" if effective_engine_running else "false",
        "runtime_last_ts": runtime_ts,
        "scan_last_ts": runtime_ts,
        "worker_last_ts": worker_last_ts,
        "worker_lag_sec": worker_lag_sec,
        "worker_status": worker_status,
        "current_selected_symbol": selected_symbol,
        "selected_symbol": selected_symbol,
        "last_symbol_switch_time": snapshot.get("last_symbol_switch_time", runtime_ts),
        "current_position_symbol": position_symbol,
        "position_status": "OPEN" if position_open else "FLAT",
        "session_realized_pnl": str(realized_pnl_value),
        "kst_daily_realized_pnl": str(runtime_realized_pnl_value),
        "kst_daily_realized_pnl_kpi": str(portfolio_snapshot.get("realized_pnl", 0.0)),
        "daily_realized_pnl": str(runtime_realized_pnl_value),
        "runtime_session_realized_pnl": str(realized_pnl_value),
        "runtime_daily_realized_pnl": str(runtime_realized_pnl_value),
        "kst_daily_trade_count": int(trade_count_value or 0),
        "scan_events_last_min": int(snapshot.get("scan_events_last_min", 0) or 0),
        "trade_executions_last_min": int(snapshot.get("trade_executions_last_min", trade_count_value) or 0),
        "engine_process_status": "RUNNING" if effective_engine_running else "STOPPED",
        "launched_symbols": launched_symbols,
        "active_symbol_count": int(runtime.get("active_symbol_count", len(active_symbols))),
        "active_symbol_count_kpi": int(runtime.get("active_symbol_count", len(active_symbols))),
        "open_positions_count": exchange_open_position_count,
        "open_position_symbols": position_symbol,
        "account_equity": str(current_equity_value),
        "account_equity_kpi": str(current_equity_value),
        "account_available_balance": str(round(available_balance_value, 6)),
        "invested_margin": str(principal_capital_value),
        "invested_margin_kpi": str(principal_capital_value),
        "unrealized_pnl_live": str(total_profit_value),
        "invested_return_pct": str(invested_return_pct),
        "total_profit_value": str(total_profit_value),
        "portfolio_total_exposure": str(portfolio_total_exposure),
        "capital_usage_ratio": str(exposure_ratio_value),
        "capital_usage_ratio_kpi": str(exposure_ratio_value),
        "current_equity_source": current_equity_source,
        "current_equity_source_label": current_equity_source_label,
        "portfolio_snapshot_ts": portfolio_snapshot.get("ts", "-"),
        "portfolio_snapshot_age_sec": portfolio_snapshot_age_sec,
        "credentials_present": "true" if credentials_present else "false",
        "api_base": "http://127.0.0.1:8100",
        "execution_mode": summary.get("profile", "TESTNET_INTRADAY_SCALP"),
        "binance_execution_mode": execution_mode_env,
        "binance_testnet_enabled": "true" if binance_testnet_enabled else "false",
        "binance_credentials_present": "true" if credentials_present else "false",
        "binance_testnet_api_base": testnet_api_base,
        "binance_api_base_is_testnet": "true" if api_base_is_testnet else "false",
        "binance_probe_mode": str(investor_probe.get("mode") or "-"),
        "binance_realtime_link_ok": "true" if realtime_exchange_link_ok else "false",
        "binance_link_status": "TESTNET_REALTIME_LINKED" if realtime_exchange_link_ok else "TESTNET_LINK_UNVERIFIED",
        "buy_count": int(snapshot.get("recent_entry_buy_count", 0) or 0),
        "sell_count": int(snapshot.get("recent_entry_sell_count", 0) or 0),
        "buy_sell_ratio": str(snapshot.get("buy_sell_ratio", "0.0")),
        "profit_factor": str(snapshot.get("profit_factor", "0")),
        "edge_score": str(runtime.get("edge_score", 0.0)),
        "active_symbols": active_symbols,
        "selected_symbols_batch": runtime.get("selected_symbols_batch") or [],
        "selected_symbol_count": len(runtime.get("selected_symbols_batch") or []),
        "universe_symbol_count": int(runtime.get("universe_symbol_count", len(runtime.get("selected_symbols_batch") or [])) or 0),
        "universe_symbols_sample": runtime.get("universe_symbols_sample") or [],
        "launched_symbols_count": len(launched_symbols),
        "symbol_switch_count": int(snapshot.get("symbol_switch_count", 0) or 0),
        "scanned_symbols": str(len(runtime.get("selected_symbols_batch") or [])),
        "scan_symbol_count": len(runtime.get("selected_symbols_batch") or []),
        "target_scan_symbols": runtime.get("max_symbol_active", 20),
        "target_max_positions": runtime.get("max_open_positions", 20),
        "target_max_position_per_symbol": 1,
        "scan_target_met": "true",
        "scan_deficit_count": 0,
        "global_kill_switch_state": str(bool(summary.get("global_kill_switch", False))).lower(),
        "global_kill_reason": summary.get("kill_reason") or "-",
        "global_api_failures": int(snapshot.get("global_api_failures", 0) or 0),
        "global_engine_errors": int(summary.get("engine_error_count", 0)),
        "global_risk_drawdown": str(snapshot.get("global_risk_drawdown", "0.0")),
        "ops_checkpoint_status": str(snapshot.get("ops_checkpoint_status", "INACTIVE_LEGACY")),
        "ops_checkpoint_source_mode": str(snapshot.get("ops_checkpoint_source_mode", "runtime_log")),
        "worker_event_recent": "true" if worker_lag_sec <= 30 else "false",
        "exchange_open_position_count": exchange_open_position_count,
        "long_position_count": long_position_count,
        "short_position_count": short_position_count,
        "total_exposure": str(portfolio_total_exposure),
        "exchange_api_ok": "true",
        "position_sync_ok": "true",
        "account_snapshot_ok": "true",
        "api_process_count": api_process_count,
        "api_python_process_count": api_python_process_count,
        "effective_role_count": int(process_info.get("effective_role_count", 0) or 0),
        "raw_runtime_process_count": int(process_info.get("raw_process_count", 0) or 0),
        "process_roles": process_roles,
        "health_warnings": health_warnings,
        "kpi_standard": "SNAPSHOT",
        "kpi_source": kpi_source_name,
        "kpi_recomputed_from": kpi_recomputed_from,
        "kpi_total_trades": int(portfolio_snapshot.get("total_trades", 0) or 0),
        "kpi_realized_pnl": str(portfolio_snapshot.get("realized_pnl", 0.0)),
        "kpi_win_rate": str(portfolio_snapshot.get("win_rate", 0.0)),
        "kpi_drawdown": str(portfolio_snapshot.get("drawdown", 0.0)),
        "runtime_stats_label": "RUNTIME_ONLY",
        "pnl_realtime": "true" if snapshot.get("pnl_realtime", True) else "false",
        "pnl_last_update_ts": snapshot.get("pnl_last_update_ts", summary.get("ts", runtime_ts)),
        "kst_daily_pnl_last_ts": snapshot.get("kst_daily_pnl_last_ts", summary.get("ts", runtime_ts)),
        "kst_daily_pnl_last_ts_kpi": snapshot.get("kst_daily_pnl_last_ts", summary.get("ts", runtime_ts)),
        "pnl_age_sec": int(snapshot.get("pnl_age_sec", 0) or 0),
        "kst_daily_pnl_window": str(snapshot.get("kst_daily_pnl_window", "KST")),
        "kst_daily_pnl_source": str(snapshot.get("kst_daily_pnl_source", pnl_source_name)),
        "daily_pnl_window": str(snapshot.get("daily_pnl_window", "session")),
        "session_pnl_source": str(snapshot.get("session_pnl_source", pnl_source_name)),
        "daily_pnl_source": str(snapshot.get("daily_pnl_source", pnl_source_name)),
        "daily_pnl_basis_note": "root_unified_runtime",
        "entry_attempts": int(phase5_status.get("ORDER_ACK_COUNT", "0") or 0),
        "trade_executions": int(phase5_status.get("ORDER_FILLED_COUNT", "0") or 0),
        "order_ack_count": int(phase5_status.get("ORDER_ACK_COUNT", "0") or 0),
        "engine_root_pid_list": str(snapshot.get("engine_root_pid_list", "-")),
        "engine_pid_list": str(snapshot.get("engine_pid_list", "-")),
        "market_regime_current": str(snapshot.get("market_regime_current", "-")),
        "market_regime_trend": str(snapshot.get("market_regime_trend", "-")),
        "market_regime_volatility": str(snapshot.get("market_regime_volatility", "-")),
        "market_regime_last_ts": snapshot.get("market_regime_last_ts", "-"),
        "binance_latest_partial_fill_ts": snapshot.get("binance_latest_partial_fill_ts", "-"),
        "binance_partial_fill_count": int(snapshot.get("binance_partial_fill_count", 0) or 0),
        "binance_partial_fill_seen": "true" if snapshot.get("binance_partial_fill_seen", False) else "false",
        "recent_entry_buy_count": int(snapshot.get("recent_entry_buy_count", 0) or 0),
        "recent_entry_sell_count": int(snapshot.get("recent_entry_sell_count", 0) or 0),
        "recent_entry_last_side": str(snapshot.get("recent_entry_last_side", "-")),
        "recent_entry_last_symbol": str(snapshot.get("recent_entry_last_symbol", "-")),
        "recent_entry_last_ts": snapshot.get("recent_entry_last_ts", "-"),
        "recent_entry_summary": "-",
        "portfolio_snapshot_realized_pnl": str(portfolio_snapshot.get("realized_pnl", 0.0)),
        "portfolio_snapshot_realized_pnl_kpi": str(portfolio_snapshot.get("realized_pnl", 0.0)),
        "account_equity_trend": "-",
        "equity_history": equity_history,
        "allocation_top": build_allocation_top(),
        "kst_daily_symbol_summary": kst_daily_symbol_stats.get("summary", {}),
        "kst_daily_symbol_stats": kst_daily_symbol_stats.get("rows", []),
        "operation_mode": "MULTI5",
        "primary_log_path": str(RUNTIME_LOG),
        "secondary_log_path": str(SUMMARY_LOG),
        "optional_worker_log_path": str(ROOT / "logs" / "runtime" / "profitmax_v1_events.jsonl"),
        "auto_boot_completed": bool(auto_boot.get("completed", False)),
        "auto_boot_message": auto_boot.get("message", "-"),
        "auto_boot_checked_at": auto_boot.get("ts", runtime_ts),
    }
    return payload


class DashboardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_bytes(self, status_code: int, body: bytes, content_type: str) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True

    def _send_text(self, status_code: int, body: str, content_type: str) -> None:
        self._send_bytes(status_code, body.encode("utf-8"), content_type)

    def do_GET(self) -> None:
        try:
            path = urlparse(self.path).path

            if path == "/api/runtime":
                self._send_text(
                    200,
                    json.dumps(build_runtime_payload(), ensure_ascii=False),
                    "application/json; charset=utf-8",
                )
                return

            if path == "/api/config":
                self._send_text(
                    200,
                    json.dumps({"refresh_interval_sec": 3}, ensure_ascii=False),
                    "application/json; charset=utf-8",
                )
                return

            if path in {"/", "/index.html"}:
                self._send_text(200, load_dashboard_html(), "text/html; charset=utf-8")
                return

            self._send_text(404, "Not Found", "text/plain; charset=utf-8")
        except Exception as exc:
            self._send_text(500, f"Dashboard error: {exc}", "text/plain; charset=utf-8")


def run_server() -> None:
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("127.0.0.1", 8788), DashboardHandler)
    try:
        print("MULTI5 dashboard listening on http://127.0.0.1:8788")
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server()
