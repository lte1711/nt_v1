from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from .multi5_config import (
        BIAS_CHECK_WINDOW,
        DRAWDDOWN_SOFT_LIMIT,
        EDGE_SCORE_THRESHOLD,
        ENGINE_ERROR_LIMIT,
        ENABLE_MARKET_REGIME,
        MAX_OPEN_POSITION,
        MAX_ACCOUNT_DRAWDOWN,
        MAX_CONSECUTIVE_LOSS,
        MAX_PORTFOLIO_EXPOSURE,
        MAX_SHORT_POSITIONS,
        MAX_SYMBOL_ACTIVE,
        MAX_SIDE_EXPOSURE,
        MAX_VOLATILITY_THRESHOLD,
        MIN_ENTRY_QUALITY_SCORE,
        MIN_LONG_RATIO,
        REGIME_TREND_THRESHOLD,
        REGIME_VOL_HIGH,
        REGIME_VOL_LOW,
        SCAN_INTERVAL_SEC,
        SHORT_BIAS_GUARD_ENABLED,
        API_FAILURE_LIMIT,
        ALLOCATION_MAX_WEIGHT,
        ALLOCATION_MIN_WEIGHT,
        ALLOCATION_OBSERVATION_MODE,
        WIN_RATE_SOFT_LIMIT,
        ENABLE_PORTFOLIO_ALLOCATION,
    )
    from .multi5_symbol_ranker import select_top_n, select_top_one, sort_by_edge
    from .multi5_engine_runtime import (
        append_jsonl,
        fetch_open_position_symbols,
        find_running_workers,
        is_api_server_reachable,
        parse_worker_symbols,
        project_root,
        run_engine,
        runtime_log_path,
        scan_log_path,
        strategy_signal_dir,
        strategy_signal_path,
        terminate_worker_symbols,
        terminate_workers,
        utc_now,
        worker_log_path,
        write_json,
        write_scan_log,
    )
    from .multi5_symbol_scanner import fetch_universe_data, resolve_symbol_universe
except ImportError:
    from multi5_config import (
        BIAS_CHECK_WINDOW,
        DRAWDDOWN_SOFT_LIMIT,
        EDGE_SCORE_THRESHOLD,
        ENGINE_ERROR_LIMIT,
        ENABLE_MARKET_REGIME,
        MAX_OPEN_POSITION,
        MAX_ACCOUNT_DRAWDOWN,
        MAX_CONSECUTIVE_LOSS,
        MAX_PORTFOLIO_EXPOSURE,
        MAX_SHORT_POSITIONS,
        MAX_SYMBOL_ACTIVE,
        MAX_SIDE_EXPOSURE,
        MAX_VOLATILITY_THRESHOLD,
        MIN_ENTRY_QUALITY_SCORE,
        MIN_LONG_RATIO,
        REGIME_TREND_THRESHOLD,
        REGIME_VOL_HIGH,
        REGIME_VOL_LOW,
        SCAN_INTERVAL_SEC,
        SHORT_BIAS_GUARD_ENABLED,
        API_FAILURE_LIMIT,
        ALLOCATION_MAX_WEIGHT,
        ALLOCATION_MIN_WEIGHT,
        ALLOCATION_OBSERVATION_MODE,
        WIN_RATE_SOFT_LIMIT,
        ENABLE_PORTFOLIO_ALLOCATION,
    )
    from multi5_symbol_ranker import select_top_n, select_top_one, sort_by_edge
    from multi5_engine_runtime import (
        append_jsonl,
        fetch_open_position_symbols,
        find_running_workers,
        is_api_server_reachable,
        parse_worker_symbols,
        project_root,
        run_engine,
        runtime_log_path,
        scan_log_path,
        strategy_signal_dir,
        strategy_signal_path,
        terminate_worker_symbols,
        terminate_workers,
        utc_now,
        worker_log_path,
        write_json,
        write_scan_log,
    )
    from multi5_symbol_scanner import fetch_universe_data, resolve_symbol_universe


def apply_symbol_diversity_penalty(
    symbol_states: list[dict[str, Any]],
    *,
    recent_selected_symbols: list[str],
    active_symbols: set[str],
    recent_blocked_symbols: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    if not symbol_states:
        return []

    recent_window = [str(symbol or "").upper().strip() for symbol in recent_selected_symbols[-12:]]
    recent_counts: dict[str, int] = {}
    for symbol in recent_window:
        if not symbol:
            continue
        recent_counts[symbol] = recent_counts.get(symbol, 0) + 1
    blocked_counts = {
        str(symbol or "").upper().strip(): max(0, int(count or 0))
        for symbol, count in (recent_blocked_symbols or {}).items()
        if str(symbol or "").strip()
    }

    adjusted: list[dict[str, Any]] = []
    for row in symbol_states:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", "")).upper().strip()
        if not symbol:
            adjusted.append(dict(row))
            continue

        row_copy = dict(row)
        active_penalty = 0.24 if symbol in active_symbols else 0.0
        repeat_penalty = min(0.48, 0.08 * recent_counts.get(symbol, 0))
        blocked_penalty = min(0.72, 0.12 * blocked_counts.get(symbol, 0))
        diversification_penalty = round(active_penalty + repeat_penalty + blocked_penalty, 6)
        adjusted_edge = max(0.0, float(row_copy.get("edge_score", 0.0) or 0.0) - diversification_penalty)
        adjusted_signal_score = float(row_copy.get("strategy_signal_score", 0.0) or 0.0)
        if row_copy.get("strategy_signal") in {"LONG", "SHORT"}:
            adjusted_signal_score = adjusted_signal_score - diversification_penalty

        row_copy["diversification_penalty"] = diversification_penalty
        row_copy["blocked_symbol_penalty"] = round(blocked_penalty, 6)
        row_copy["edge_score"] = round(adjusted_edge, 6)
        if diversification_penalty > 0.0 and adjusted_edge <= 0.0:
            row_copy["strategy_signal"] = "HOLD"
            adjusted_signal_score = min(0.0, adjusted_signal_score)
            row_copy["selection_neutralized"] = True
        row_copy["strategy_signal_score"] = round(adjusted_signal_score, 6)
        adjusted.append(row_copy)
    return adjusted


def collect_signal_target_symbols(
    top_candidates: list[dict[str, Any]],
    *,
    active_symbols: set[str],
    open_position_symbols: set[str],
    selected_symbol: str | None = None,
) -> set[str]:
    targets: set[str] = set()
    for row in top_candidates:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", "")).upper().strip()
        if symbol:
            targets.add(symbol)
    targets.update(str(symbol).upper().strip() for symbol in active_symbols if str(symbol).strip())
    targets.update(str(symbol).upper().strip() for symbol in open_position_symbols if str(symbol).strip())
    if selected_symbol:
        targets.add(str(selected_symbol).upper().strip())
    return {symbol for symbol in targets if symbol}


def recover_missing_position_workers(
    *,
    open_position_symbols: set[str],
    worker_symbols: set[str],
    state_by_symbol: dict[str, dict[str, Any]],
    engine_session_hours: float,
    max_position_per_symbol: int,
    launch_cooldown_sec: int,
    last_launch_at: dict[str, datetime],
) -> tuple[list[str], list[str]]:
    missing_symbols = sorted(
        symbol
        for symbol in open_position_symbols
        if symbol and symbol not in worker_symbols
    )
    launched_symbols: list[str] = []
    launched_strategy_units: list[str] = []
    now = utc_now()

    for symbol in missing_symbols:
        prev = last_launch_at.get(symbol)
        if prev is not None and (now - prev).total_seconds() < launch_cooldown_sec:
            continue

        row = state_by_symbol.get(symbol, {})
        strategy_id = str(row.get("strategy_id", "")).strip() or "momentum_intraday_v1"
        strategy_unit = str(row.get("strategy_unit", "")).strip() or "BALANCED_INTRADAY_MOMENTUM"
        strategy_signal = str(row.get("strategy_signal", "HOLD")).upper().strip()
        strategy_signal_score = float(row.get("strategy_signal_score", 0.0) or 0.0)
        edge_score = float(row.get("edge_score", 0.0) or 0.0)
        base_edge_score = float(row.get("base_edge_score", edge_score) or edge_score)
        take_profit_pct = float(row.get("take_profit_pct", 0.012) or 0.012)
        stop_loss_pct = float(row.get("stop_loss_pct", 0.006) or 0.006)
        signal_path = strategy_signal_path(symbol, strategy_id)

        write_json(
            signal_path,
            {
                "ts": now.isoformat(),
                "symbol": symbol,
                "strategy_id": strategy_id,
                "strategy_unit": strategy_unit,
                "strategy_signal": strategy_signal,
                "strategy_signal_score": strategy_signal_score,
                "edge_score": edge_score,
                "base_edge_score": base_edge_score,
                "roc_10": float(row.get("roc_10", 0.0) or 0.0),
                "rsi_14": float(row.get("rsi_14", 0.0) or 0.0),
                "sma_20": float(row.get("sma_20", 0.0) or 0.0),
                "close": float(row.get("close", 0.0) or 0.0),
                "volume_ratio": float(row.get("volume_ratio", 0.0) or 0.0),
                "trend_strength": float(row.get("trend_strength", 0.0) or 0.0),
                "time_window_mode": str(row.get("time_window_mode", "BLOCKED")),
                "shock_move_1m_pct": float(row.get("shock_move_1m_pct", 0.0) or 0.0),
                "shock_move_2m_pct": float(row.get("shock_move_2m_pct", 0.0) or 0.0),
                "shock_move_3m_pct": float(row.get("shock_move_3m_pct", 0.0) or 0.0),
                "trigger_direction": str(row.get("trigger_direction", "")),
                "take_profit_pct": take_profit_pct,
                "stop_loss_pct": stop_loss_pct,
            },
        )
        run_engine(
            symbol,
            session_hours=engine_session_hours,
            max_positions=max_position_per_symbol,
            strategy_unit=strategy_unit,
            strategy_signal_path_value=signal_path,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
        )
        last_launch_at[symbol] = now
        launched_symbols.append(symbol)
        launched_strategy_units.append(strategy_id)

    return launched_symbols, launched_strategy_units


def read_recent_jsonl_rows(path: Path, *, max_bytes: int = 1048576, max_rows: int = 2000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            raw = handle.read().decode("utf-8", errors="replace")
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    for line in raw.splitlines()[-max_rows:]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def collect_recent_blocked_symbols(window_minutes: int = 20) -> dict[str, int]:
    cutoff = utc_now() - timedelta(minutes=max(1, int(window_minutes)))
    blocked_counts: dict[str, int] = {}
    for row in read_recent_jsonl_rows(worker_log_path()):
        try:
            ts = datetime.fromisoformat(str(row.get("ts", "")))
        except Exception:
            continue
        if ts < cutoff:
            continue
        event_type = str(row.get("event_type", ""))
        if event_type not in {"ENTRY_TO_SUBMIT_BLOCKED", "STRATEGY_BLOCKED"}:
            continue
        payload = row.get("payload", {}) or {}
        detail = str(payload.get("detail") or payload.get("block_reason") or payload.get("reason") or "").lower()
        if "short_bias_guard" not in detail:
            continue
        symbol = str(payload.get("symbol") or row.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        blocked_counts[symbol] = blocked_counts.get(symbol, 0) + 1
    return blocked_counts




def run_loop(
    runtime_minutes: int,
    scan_interval_sec: int,
    engine_session_hours: float,
    max_open_positions: int,
    max_symbol_active: int,
    max_position_per_symbol: int,
    launch_cooldown_sec: int,
) -> dict[str, Any]:
    end_at = utc_now() + timedelta(minutes=runtime_minutes)
    scan_events_count = 0
    engine_entry_attempts = 0
    selected_history: list[str] = []
    last_selected: str | None = None
    last_launch_at: dict[str, datetime] = {}
    worker_grace_sec = max(launch_cooldown_sec, 300)

    while utc_now() < end_at:
        resolved_universe = resolve_symbol_universe()
        worker_rows = find_running_workers()
        worker_symbols = parse_worker_symbols(worker_rows)
        open_position_symbols = fetch_open_position_symbols()
        active_symbols = set(open_position_symbols).union(worker_symbols)
        recent_blocked_symbols = collect_recent_blocked_symbols()
        states = fetch_universe_data(resolved_universe)
        states = apply_symbol_diversity_penalty(
            states,
            recent_selected_symbols=selected_history,
            active_symbols=active_symbols,
            recent_blocked_symbols=recent_blocked_symbols,
        )
        ranked = sort_by_edge(states)
        top = select_top_one(states)
        top_candidates = select_top_n(states, limit=min(max_open_positions, max_symbol_active))
        api_server_reachable = is_api_server_reachable()
        selected_symbol = top.get("SELECTED_SYMBOL") if top else None
        edge_score = float(top.get("EDGE_SCORE", 0.0)) if top else 0.0
        signal_target_symbols = collect_signal_target_symbols(
            top_candidates,
            active_symbols=active_symbols,
            open_position_symbols=open_position_symbols,
            selected_symbol=selected_symbol,
        )
        selected_candidate_symbols = {
            str(row.get("symbol", "")).upper().strip()
            for row in top_candidates
            if isinstance(row, dict) and row.get("symbol")
        }

        write_scan_log(ranked, selected_symbol, selected_candidate_symbols)
        scan_events_count += len(ranked)

        if selected_symbol:
            selected_history.append(selected_symbol)
            if selected_symbol != last_selected:
                last_selected = selected_symbol
        worker_grace_active = False
        if worker_symbols:
            for sym in worker_symbols:
                launched_at = last_launch_at.get(sym)
                if launched_at is None:
                    worker_grace_active = True
                    break
                if (utc_now() - launched_at).total_seconds() < worker_grace_sec:
                    worker_grace_active = True
                    break

        if worker_symbols and not open_position_symbols:
            if worker_grace_active or (selected_candidate_symbols and worker_symbols.intersection(selected_candidate_symbols)):
                active_symbols = set(worker_symbols)
            elif len(worker_symbols) >= min(max_open_positions, max_symbol_active):
                terminate_workers(worker_rows)
                time.sleep(1)
                worker_rows = find_running_workers()
                worker_symbols = parse_worker_symbols(worker_rows)
                active_symbols = set(open_position_symbols).union(worker_symbols)

        allowed_active_cap = min(max_open_positions, max_symbol_active)
        if len(active_symbols) > allowed_active_cap:
            excess_symbols = [sym for sym in sorted(worker_symbols) if sym not in open_position_symbols]
            excess_count = len(active_symbols) - allowed_active_cap
            if excess_count > 0:
                terminate_worker_symbols(worker_rows, set(excess_symbols[:excess_count]))
                time.sleep(1)
                worker_rows = find_running_workers()
                worker_symbols = parse_worker_symbols(worker_rows)
                active_symbols = set(open_position_symbols).union(worker_symbols)

        state_by_symbol = {
            str(row.get("symbol", "")).upper().strip(): row
            for row in states
            if isinstance(row, dict) and row.get("symbol")
        }
        entry_attempted = False
        launched_symbols: list[str] = []
        launched_strategy_units: list[str] = []
        recovered_symbols, recovered_strategy_units = recover_missing_position_workers(
            open_position_symbols=open_position_symbols,
            worker_symbols=worker_symbols,
            state_by_symbol=state_by_symbol,
            engine_session_hours=engine_session_hours,
            max_position_per_symbol=max_position_per_symbol,
            launch_cooldown_sec=launch_cooldown_sec,
            last_launch_at=last_launch_at,
        )
        if recovered_symbols:
            worker_symbols.update(recovered_symbols)
            active_symbols = set(open_position_symbols).union(worker_symbols)
            launched_symbols.extend(recovered_symbols)
            launched_strategy_units.extend(recovered_strategy_units)
            entry_attempted = True
        for signal_symbol in sorted(signal_target_symbols):
            row = state_by_symbol.get(signal_symbol)
            if not row:
                continue
            strategy_id = str(row.get("strategy_id", "")).strip() or "momentum_intraday_v1"
            strategy_unit = str(row.get("strategy_unit", "")).strip() or "BALANCED_INTRADAY_MOMENTUM"
            signal_path = strategy_signal_path(signal_symbol, strategy_id)
            write_json(
                signal_path,
                {
                    "ts": utc_now().isoformat(),
                    "symbol": signal_symbol,
                    "strategy_id": strategy_id,
                    "strategy_unit": strategy_unit,
                    "strategy_signal": str(row.get("strategy_signal", "HOLD")).upper().strip(),
                    "strategy_signal_score": float(row.get("strategy_signal_score", 0.0) or 0.0),
                    "edge_score": float(row.get("edge_score", 0.0) or 0.0),
                    "base_edge_score": float(row.get("base_edge_score", 0.0) or 0.0),
                    "roc_10": float(row.get("roc_10", 0.0) or 0.0),
                    "rsi_14": float(row.get("rsi_14", 0.0) or 0.0),
                    "sma_20": float(row.get("sma_20", 0.0) or 0.0),
                    "close": float(row.get("close", 0.0) or 0.0),
                    "volume_ratio": float(row.get("volume_ratio", 0.0) or 0.0),
                    "trend_strength": float(row.get("trend_strength", 0.0) or 0.0),
                    "time_window_mode": str(row.get("time_window_mode", "BLOCKED")),
                    "shock_move_1m_pct": float(row.get("shock_move_1m_pct", 0.0) or 0.0),
                    "shock_move_2m_pct": float(row.get("shock_move_2m_pct", 0.0) or 0.0),
                    "shock_move_3m_pct": float(row.get("shock_move_3m_pct", 0.0) or 0.0),
                    "trigger_direction": str(row.get("trigger_direction", "")),
                    "take_profit_pct": float(row.get("take_profit_pct", 0.012) or 0.012),
                    "stop_loss_pct": float(row.get("stop_loss_pct", 0.006) or 0.006),
                },
            )
        if api_server_reachable:
            for candidate in top_candidates:
                candidate_symbol = str(candidate.get("symbol", "")).upper().strip()
                candidate_edge_score = float(candidate.get("edge_score", 0.0) or 0.0)
                strategy_signal = str(candidate.get("strategy_signal", "HOLD")).upper().strip()
                strategy_id = str(candidate.get("strategy_id", "")).strip() or "momentum_intraday_v1"
                strategy_unit = str(candidate.get("strategy_unit", "")).strip() or "BALANCED_INTRADAY_MOMENTUM"
                strategy_signal_score = float(candidate.get("strategy_signal_score", 0.0) or 0.0)
                take_profit_pct = float(candidate.get("take_profit_pct", 0.012) or 0.012)
                stop_loss_pct = float(candidate.get("stop_loss_pct", 0.006) or 0.006)
                signal_path = strategy_signal_path(candidate_symbol, strategy_id)
                if (
                    not candidate_symbol
                    or candidate_edge_score < EDGE_SCORE_THRESHOLD
                    or strategy_signal not in {"LONG", "SHORT"}
                ):
                    continue
                if len(active_symbols) >= allowed_active_cap:
                    break
                symbol_active = candidate_symbol in open_position_symbols or candidate_symbol in worker_symbols or candidate_symbol in active_symbols
                can_launch_symbol = (not symbol_active) or (max_position_per_symbol > 1)
                cooldown_ready = True
                prev = last_launch_at.get(candidate_symbol)
                if prev is not None:
                    cooldown_ready = (utc_now() - prev).total_seconds() >= launch_cooldown_sec
                if not can_launch_symbol or not cooldown_ready:
                    continue
                run_engine(
                    candidate_symbol,
                    session_hours=engine_session_hours,
                    max_positions=max_position_per_symbol,
                    strategy_unit=strategy_unit,
                    strategy_signal_path_value=signal_path,
                    take_profit_pct=take_profit_pct,
                    stop_loss_pct=stop_loss_pct,
                )
                last_launch_at[candidate_symbol] = utc_now()
                active_symbols.add(candidate_symbol)
                launched_symbols.append(candidate_symbol)
                launched_strategy_units.append(strategy_id)
                engine_entry_attempts += 1
                entry_attempted = True

        selected_strategy_signal = str(top.get("STRATEGY_SIGNAL", "HOLD")).upper() if top else "HOLD"
        selected_strategy_id = str(top.get("STRATEGY_ID", "")) if top else ""
        append_jsonl(
            runtime_log_path(),
            {
                "ts": utc_now().isoformat(),
                "selected_symbol": selected_symbol,
                "selected_symbols_batch": sorted(selected_candidate_symbols),
                "universe_symbol_count": len(resolved_universe),
                "universe_symbols_sample": resolved_universe[:20],
                "edge_score": edge_score,
                "selected_strategy_id": selected_strategy_id,
                "selected_strategy_signal": selected_strategy_signal,
                "selected_diversification_penalty": float(top.get("diversification_penalty", 0.0)) if top else 0.0,
                "selected_blocked_symbol_penalty": float(top.get("blocked_symbol_penalty", 0.0)) if top else 0.0,
                "engine_running": bool(worker_rows),
                "engine_entry_attempted": entry_attempted,
                "launched_symbols": launched_symbols,
                "launched_strategy_units": launched_strategy_units,
                "recovered_position_symbols": recovered_symbols,
                "api_server_reachable": api_server_reachable,
                "active_symbol_count": len(active_symbols),
                "active_symbols": sorted(active_symbols),
                "max_symbol_active": max_symbol_active,
                "max_open_positions": max_open_positions,
            },
        )
        time.sleep(scan_interval_sec)

    selected_symbol_changes = 0
    for i in range(1, len(selected_history)):
        if selected_history[i] != selected_history[i - 1]:
            selected_symbol_changes += 1

    return {
        "scan_events_count": scan_events_count,
        "selected_symbol_changes": selected_symbol_changes,
        "engine_entry_attempts": engine_entry_attempts,
        "last_selected_symbol": last_selected or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="MULTI5 wrapper runtime entry")
    parser.add_argument("--runtime-minutes", type=int, default=5)
    parser.add_argument("--scan-interval-sec", type=int, default=SCAN_INTERVAL_SEC)
    parser.add_argument("--engine-session-hours", type=float, default=2.0)
    parser.add_argument("--max-open-positions", type=int, default=MAX_OPEN_POSITION)
    parser.add_argument("--max-symbol-active", type=int, default=MAX_SYMBOL_ACTIVE)
    parser.add_argument("--max-position-per-symbol", type=int, default=1)
    parser.add_argument("--launch-cooldown-sec", type=int, default=120)
    args = parser.parse_args()

    result = run_loop(
        runtime_minutes=max(1, args.runtime_minutes),
        scan_interval_sec=max(1, args.scan_interval_sec),
        engine_session_hours=max(0.05, args.engine_session_hours),
        max_open_positions=max(1, args.max_open_positions),
        max_symbol_active=max(1, args.max_symbol_active),
        max_position_per_symbol=max(1, args.max_position_per_symbol),
        launch_cooldown_sec=max(1, args.launch_cooldown_sec),
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
