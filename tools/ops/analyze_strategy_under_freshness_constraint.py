from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(r"C:\nt_v1")
EVENT_LOG = PROJECT_ROOT / "logs/runtime/profitmax_v1_events.jsonl"
RUNTIME_LOG = PROJECT_ROOT / "logs/runtime/multi5_runtime_events.jsonl"
DETAIL_STATE = PROJECT_ROOT / "reports/2026-03-28/codex_execution_reports/STEP_BAEKSEOL_STRATEGY_UNDER_FRESHNESS_CONSTRAINT_1.detailed_state.json"
REPORT_PATH = PROJECT_ROOT / "reports/2026-03-28/codex_execution_reports/STEP_BAEKSEOL_STRATEGY_UNDER_FRESHNESS_CONSTRAINT_1.txt"
SUMMARY_PATH = PROJECT_ROOT / "reports/2026-03-28/codex_execution_reports/STEP_BAEKSEOL_STRATEGY_UNDER_FRESHNESS_CONSTRAINT_1.summary.json"

WINDOW_START = datetime.fromisoformat("2026-03-28T04:40:00+00:00")
WINDOW_END = datetime.fromisoformat("2026-03-28T06:40:00+00:00")


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def safe_mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 6) if values else None


def classify_exit(reason: str | None) -> str:
    normalized = str(reason or "").strip().lower()
    if normalized in {"fixed_tp", "tp", "take_profit"}:
        return "TP_EXIT"
    if normalized in {"hard_stop", "sl", "stop_loss"}:
        return "SL_EXIT"
    if normalized in {"timeout_exit", "timeout", "time_exit"}:
        return "TIMEOUT_EXIT"
    return "OTHER"


def main() -> None:
    issues = {}
    if DETAIL_STATE.exists():
        issues = json.loads(DETAIL_STATE.read_text(encoding="utf-8-sig"))

    entry_signals_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    preorders_by_trace: dict[str, dict[str, Any]] = {}
    order_filled_entries_by_trace: dict[str, dict[str, Any]] = {}
    closed_by_trace: dict[str, dict[str, Any]] = {}
    realized_by_trace: dict[str, float] = {}
    duration_by_trace: dict[str, float] = {}
    hold_by_trace: dict[str, float] = {}
    exit_reason_by_trace: dict[str, str] = {}
    trade_exec_exit_by_trace: dict[str, dict[str, Any]] = {}

    with EVENT_LOG.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except Exception:
                continue
            ts = parse_ts(row.get("ts"))
            if ts is None or not (WINDOW_START <= ts <= WINDOW_END):
                continue

            event_type = row.get("event_type")
            symbol = row.get("symbol")
            payload = row.get("payload", {}) or {}

            if event_type == "ENTRY_SIGNAL":
                entry_signals_by_symbol[str(symbol)].append(
                    {
                        "ts": ts,
                        "symbol": symbol,
                        "strategy_id": payload.get("strategy_id"),
                        "signal_score": payload.get("signal_score"),
                    }
                )
            elif event_type == "DATA_FLOW_TRACE_PRE_ORDER":
                trace_id = payload.get("trace_id")
                if trace_id:
                    preorders_by_trace[str(trace_id)] = {
                        "ts": ts,
                        "symbol": symbol,
                        "total_delay_ms_to_order": payload.get("total_delay_ms_to_order"),
                        "decision_to_order_delay_ms": payload.get("decision_to_order_delay_ms"),
                    }
            elif event_type == "ORDER_FILLED":
                trace_id = payload.get("trace_id")
                if trace_id and not bool(payload.get("reduceOnly", False)):
                    order_filled_entries_by_trace[str(trace_id)] = {
                        "ts": ts,
                        "symbol": symbol,
                        "side": payload.get("side"),
                        "qty": payload.get("entry_filled_qty") or payload.get("qty"),
                    }
            elif event_type == "POSITION_CLOSED":
                trace_id = payload.get("trace_id")
                if trace_id:
                    closed_by_trace[str(trace_id)] = {
                        "ts": ts,
                        "symbol": symbol,
                        "entry_price": payload.get("entry_price"),
                        "exit_price": payload.get("exit_price"),
                        "qty": payload.get("qty"),
                        "position_side": payload.get("position_side"),
                        "reason": payload.get("reason"),
                    }
            elif event_type == "REALIZED_PNL":
                trace_id = payload.get("trace_id")
                if trace_id:
                    realized_by_trace[str(trace_id)] = float(payload.get("pnl", 0.0) or 0.0)
            elif event_type == "TRADE_DURATION":
                trace_id = payload.get("trace_id")
                if trace_id:
                    duration_by_trace[str(trace_id)] = float(payload.get("duration_seconds", 0.0) or 0.0)
            elif event_type == "POSITION_HOLD_TIME":
                trace_id = payload.get("trace_id")
                if trace_id:
                    hold_by_trace[str(trace_id)] = float(payload.get("hold_seconds", 0.0) or 0.0)
            elif event_type == "EXIT_REASON":
                trace_id = payload.get("trace_id")
                if trace_id:
                    exit_reason_by_trace[str(trace_id)] = str(payload.get("exit_reason") or "")
            elif event_type == "TRADE_EXECUTED":
                trace_id = payload.get("trace_id")
                if trace_id and str(payload.get("execution_type")) == "EXIT":
                    trade_exec_exit_by_trace[str(trace_id)] = {
                        "pnl": float(payload.get("pnl", 0.0) or 0.0),
                        "exit_price": payload.get("exit_price"),
                    }

    trades: list[dict[str, Any]] = []
    for trace_id, closed in closed_by_trace.items():
        symbol = str(closed.get("symbol"))
        entry_info = order_filled_entries_by_trace.get(trace_id, {})
        pre = preorders_by_trace.get(trace_id, {})
        pnl = realized_by_trace.get(trace_id)
        if pnl is None and trace_id in trade_exec_exit_by_trace:
            pnl = trade_exec_exit_by_trace[trace_id]["pnl"]
        hold_sec = duration_by_trace.get(trace_id, hold_by_trace.get(trace_id))
        exit_reason = exit_reason_by_trace.get(trace_id, str(closed.get("reason") or ""))

        signal_age_at_entry = None
        entry_signal_ts = None
        if symbol in entry_signals_by_symbol and entry_info.get("ts"):
            candidates = [row for row in entry_signals_by_symbol[symbol] if row["ts"] <= entry_info["ts"]]
            if candidates:
                chosen = max(candidates, key=lambda row: row["ts"])
                entry_signal_ts = chosen["ts"]
                signal_age_at_entry = round((entry_info["ts"] - chosen["ts"]).total_seconds(), 3)

        trades.append(
            {
                "trace_id": trace_id,
                "symbol": symbol,
                "entry_timestamp": entry_info.get("ts").isoformat() if entry_info.get("ts") else None,
                "exit_timestamp": closed.get("ts").isoformat() if closed.get("ts") else None,
                "entry_price": closed.get("entry_price"),
                "exit_price": closed.get("exit_price"),
                "side": closed.get("position_side"),
                "qty": closed.get("qty"),
                "realized_pnl": pnl,
                "exit_reason": exit_reason,
                "exit_class": classify_exit(exit_reason),
                "hold_time_sec": hold_sec,
                "hold_time_min": round(hold_sec / 60.0, 3) if hold_sec is not None else None,
                "total_delay_ms_to_order": pre.get("total_delay_ms_to_order"),
                "decision_to_order_delay_ms": pre.get("decision_to_order_delay_ms"),
                "entry_signal_timestamp": entry_signal_ts.isoformat() if entry_signal_ts else None,
                "signal_age_at_entry_sec": signal_age_at_entry,
            }
        )

    trade_count = len(trades)
    pnls = [float(t["realized_pnl"]) for t in trades if t["realized_pnl"] is not None]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = round(win_count / trade_count, 6) if trade_count else 0.0
    avg_win = safe_mean(wins)
    avg_loss = safe_mean(losses)
    profit_factor = round(sum(wins) / abs(sum(losses)), 6) if losses else None
    expectancy = round(sum(pnls) / trade_count, 6) if trade_count else None

    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for pnl in pnls:
        cumulative += pnl
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)

    holds = [float(t["hold_time_sec"]) for t in trades if t["hold_time_sec"] is not None]
    timeout_trades = [t for t in trades if t["exit_class"] == "TIMEOUT_EXIT"]
    timeout_pnls = [float(t["realized_pnl"]) for t in timeout_trades if t["realized_pnl"] is not None]
    signal_ages = [float(t["signal_age_at_entry_sec"]) for t in trades if t["signal_age_at_entry_sec"] is not None]
    delays = [float(t["total_delay_ms_to_order"]) for t in trades if t["total_delay_ms_to_order"] is not None]

    exit_distribution = Counter(t["exit_class"] for t in trades)
    win_under_5 = sum(1 for t in trades if (t["realized_pnl"] or 0) > 0 and (t["hold_time_sec"] or 0) < 300)
    win_overeq_5 = sum(1 for t in trades if (t["realized_pnl"] or 0) > 0 and (t["hold_time_sec"] or 0) >= 300)

    summary = {
        "window_start_utc": WINDOW_START.isoformat(),
        "window_end_utc": WINDOW_END.isoformat(),
        "trade_count": trade_count,
        "wins": win_count,
        "losses": loss_count,
        "win_rate": win_rate,
        "realized_pnl": round(sum(pnls), 6),
        "drawdown": round(max_drawdown, 6),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "hold_time_avg_sec": safe_mean(holds),
        "hold_time_distribution_sec": {
            "min": min(holds) if holds else None,
            "median": round(statistics.median(holds), 6) if holds else None,
            "max": max(holds) if holds else None,
        },
        "exit_reason_distribution": dict(exit_distribution),
        "timeout_exit_ratio": round(len(timeout_trades) / trade_count, 6) if trade_count else None,
        "timeout_trade_avg_pnl": safe_mean(timeout_pnls),
        "delay_vs_outcome": [
            {
                "trace_id": t["trace_id"],
                "symbol": t["symbol"],
                "total_delay_ms_to_order": t["total_delay_ms_to_order"],
                "realized_pnl": t["realized_pnl"],
            }
            for t in trades
        ],
        "signal_age_at_entry_avg_sec": safe_mean(signal_ages),
        "signal_age_at_entry_values_sec": signal_ages,
        "winner_hold_under_5min": win_under_5,
        "winner_hold_overeq_5min": win_overeq_5,
        "issues": issues.get("counters", {}) if issues else {},
        "trades": trades,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("[FACT]")
    lines.append(f"- observation_window_utc = {WINDOW_START.isoformat()} -> {WINDOW_END.isoformat()}")
    lines.append(f"- total_trades = {trade_count}")
    lines.append(f"- wins = {win_count}")
    lines.append(f"- losses = {loss_count}")
    lines.append(f"- win_rate = {win_rate}")
    lines.append(f"- realized_pnl = {round(sum(pnls), 6)}")
    lines.append(f"- drawdown = {round(max_drawdown, 6)}")
    lines.append(f"- avg_win = {avg_win}")
    lines.append(f"- avg_loss = {avg_loss}")
    lines.append(f"- profit_factor = {profit_factor}")
    lines.append(f"- expectancy = {expectancy}")
    lines.append(f"- hold_time_avg_sec = {safe_mean(holds)}")
    lines.append(f"- hold_time_distribution_sec = {summary['hold_time_distribution_sec']}")
    lines.append(f"- exit_reason_distribution = {dict(exit_distribution)}")
    lines.append(f"- timeout_exit_ratio = {summary['timeout_exit_ratio']}")
    lines.append(f"- timeout_trade_avg_pnl = {summary['timeout_trade_avg_pnl']}")
    lines.append(f"- signal_age_at_entry_avg_sec = {summary['signal_age_at_entry_avg_sec']}")
    lines.append(f"- signal_age_at_entry_values_sec = {signal_ages}")
    lines.append(f"- winner_hold_under_5min = {win_under_5}")
    lines.append(f"- winner_hold_overeq_5min = {win_overeq_5}")
    lines.append(f"- issue_counters = {summary['issues']}")
    lines.append("")
    lines.append("[CRITICAL_FINDINGS]")
    if trade_count < 30:
        lines.append(f"- MIN_TRADES >= 30 condition FAILED: only {trade_count} closed trades in locked-profile window")
    lines.append(f"- EXPECTANCY < 0 = {expectancy is not None and expectancy < 0}")
    lines.append(f"- AVG_WIN < abs(AVG_LOSS) = {avg_win is not None and avg_loss is not None and avg_win < abs(avg_loss)}")
    lines.append(f"- TIMEOUT_EXIT_RATIO > 30% = {summary['timeout_exit_ratio'] is not None and summary['timeout_exit_ratio'] > 0.3}")
    lines.append(f"- signal_age_at_entry ~= 8s class = {summary['signal_age_at_entry_avg_sec'] is not None and 5 <= summary['signal_age_at_entry_avg_sec'] <= 12}")
    lines.append(f"- delay_vs_outcome = {summary['delay_vs_outcome']}")
    lines.append("")
    lines.append("[INFERENCE]")
    if trade_count < 30:
        lines.append("- locked-profile window produced insufficient closed-trade sample for final strategy PASS/FAIL confidence")
    lines.append("- current report is evidence-grade for environment behavior, but low-confidence for full strategy quality because sample is small")
    lines.append("")
    lines.append("[FINAL_JUDGMENT]")
    if trade_count < 30:
        lines.append("- STRATEGY_STATUS = INSUFFICIENT_SAMPLE")
        lines.append("- NEXT_ACTION = continue locked-profile observation until 30+ closed trades before final strategic verdict")
    else:
        lines.append(f"- STRATEGY_STATUS = {'FAIL' if expectancy is not None and expectancy < 0 else 'PASS'}")
        lines.append("- NEXT_ACTION = review timeout / signal freshness / strategy redesign gate")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

