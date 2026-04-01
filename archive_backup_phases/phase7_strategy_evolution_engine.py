from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

KST = timezone(timedelta(hours=9))


@dataclass
class TradeRecord:
    trace_id: str
    symbol: str
    strategy_id: str
    regime: str
    entry_ts: datetime
    exit_ts: datetime
    holding_sec: float
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    entry_signal_score: float
    entry_expected_edge: float
    exit_reason: str


def parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    s = str(value)
    try:
        # Handles +00:00 and Z forms
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except Exception:
            continue
    return rows


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def build_trade_data(profitmax_events: list[dict[str, Any]]) -> tuple[list[TradeRecord], list[dict[str, Any]], dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    strategy_events: list[dict[str, Any]] = []

    signal_count = 0
    entry_count = 0
    exit_count = 0

    for ev in profitmax_events:
        ts = parse_ts(ev.get("ts"))
        event_type = str(ev.get("event_type", ""))
        symbol = str(ev.get("symbol", ""))
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}

        if event_type == "ENTRY_SIGNAL":
            signal_count += 1
            strategy_events.append(
                {
                    "ts": ts.isoformat() if ts else None,
                    "event_type": event_type,
                    "symbol": symbol,
                    "trace_id": payload.get("trace_id"),
                    "strategy_id": payload.get("strategy_id", "unknown"),
                    "regime": payload.get("regime", "unknown"),
                    "signal_score": safe_float(payload.get("signal_score")),
                    "expected_edge": safe_float(payload.get("expected_edge")),
                }
            )

        if event_type == "ENTRY":
            trace_id = str(payload.get("trace_id", "")).strip()
            if trace_id:
                entry_count += 1
                entries[trace_id] = {
                    "ts": ts,
                    "symbol": symbol,
                    "strategy_id": str(payload.get("strategy_id", "unknown")),
                    "regime": str(payload.get("regime", "unknown")),
                    "side": str(payload.get("side", "")),
                    "qty": safe_float(payload.get("qty")),
                    "entry_price": safe_float(payload.get("entry_price")),
                    "signal_score": safe_float(payload.get("signal_score")),
                    "expected_edge": safe_float(payload.get("expected_edge")),
                }

        if event_type == "EXIT":
            exit_count += 1

    trades: list[TradeRecord] = []
    for ev in profitmax_events:
        event_type = str(ev.get("event_type", ""))
        if event_type != "EXIT":
            continue
        ts = parse_ts(ev.get("ts"))
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        trace_id = str(payload.get("trace_id", "")).strip()
        if not trace_id or trace_id not in entries:
            continue

        ent = entries[trace_id]
        entry_ts = ent.get("ts")
        if not isinstance(entry_ts, datetime) or not isinstance(ts, datetime):
            continue

        holding_sec = max((ts - entry_ts).total_seconds(), 0.0)
        trades.append(
            TradeRecord(
                trace_id=trace_id,
                symbol=str(ent.get("symbol", "")),
                strategy_id=str(ent.get("strategy_id", "unknown")),
                regime=str(ent.get("regime", "unknown")),
                entry_ts=entry_ts,
                exit_ts=ts,
                holding_sec=holding_sec,
                entry_price=safe_float(ent.get("entry_price")),
                exit_price=safe_float(payload.get("exit_price")),
                qty=safe_float(payload.get("qty")) or safe_float(ent.get("qty")),
                pnl=safe_float(payload.get("pnl")),
                entry_signal_score=safe_float(ent.get("signal_score")),
                entry_expected_edge=safe_float(ent.get("expected_edge")),
                exit_reason=str(payload.get("reason", "unknown")),
            )
        )

    counters = {
        "signal_count": signal_count,
        "entry_count": entry_count,
        "exit_count": exit_count,
    }
    return trades, strategy_events, counters


def compute_metrics(trades: list[TradeRecord], signal_count: int) -> dict[str, Any]:
    trade_count = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]

    win_rate = (len(wins) / trade_count) if trade_count else 0.0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss_abs = abs(sum(t.pnl for t in losses))
    profit_factor = (gross_profit / gross_loss_abs) if gross_loss_abs > 0 else (999.0 if gross_profit > 0 else 0.0)

    avg_win = mean([t.pnl for t in wins]) if wins else 0.0
    avg_loss_abs = abs(mean([t.pnl for t in losses])) if losses else 0.0
    avg_risk_reward = (avg_win / avg_loss_abs) if avg_loss_abs > 0 else (999.0 if avg_win > 0 else 0.0)

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: x.exit_ts):
        equity += t.pnl
        peak = max(peak, equity)
        dd = peak - equity
        max_dd = max(max_dd, dd)

    signal_success_rate = (trade_count / signal_count) if signal_count > 0 else 0.0

    return {
        "trade_count": trade_count,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "average_risk_reward": avg_risk_reward,
        "max_drawdown": max_dd,
        "signal_success_rate": signal_success_rate,
        "gross_profit": gross_profit,
        "gross_loss_abs": gross_loss_abs,
        "net_pnl": sum(t.pnl for t in trades),
        "avg_holding_sec": mean([t.holding_sec for t in trades]) if trades else 0.0,
    }


def strategy_ranking(trades: list[TradeRecord]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[TradeRecord]] = {}
    for t in trades:
        key = (t.strategy_id, t.regime)
        grouped.setdefault(key, []).append(t)

    ranking: list[dict[str, Any]] = []
    for (strategy_id, regime), rows in grouped.items():
        m = compute_metrics(rows, signal_count=len(rows))
        win_norm = m["win_rate"]
        pf_norm = min(m["profit_factor"] / 3.0, 1.0)
        dd_norm = 1.0 - min(m["max_drawdown"] / 5.0, 1.0)
        signal_norm = m["signal_success_rate"]
        score = 100.0 * (0.35 * win_norm + 0.30 * pf_norm + 0.20 * dd_norm + 0.15 * signal_norm)

        ranking.append(
            {
                "strategy_id": strategy_id,
                "market_regime": regime,
                "trade_count": m["trade_count"],
                "win_rate": round(m["win_rate"], 6),
                "profit_factor": round(m["profit_factor"], 6),
                "average_risk_reward": round(m["average_risk_reward"], 6),
                "max_drawdown": round(m["max_drawdown"], 6),
                "signal_success_rate": round(m["signal_success_rate"], 6),
                "strategy_score": round(score, 4),
                "net_pnl": round(m["net_pnl"], 6),
            }
        )

    ranking.sort(key=lambda x: x["strategy_score"], reverse=True)
    return ranking


def optimize_params(trades: list[TradeRecord], counters: dict[str, Any]) -> dict[str, Any]:
    thresholds = [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
    symbol_options = [2, 3, 4, 5]

    best = None
    tested: list[dict[str, Any]] = []

    for th in thresholds:
        candidate = [t for t in trades if t.entry_expected_edge >= th]
        m = compute_metrics(candidate, signal_count=max(counters.get("signal_count", 0), 1))

        for msa in symbol_options:
            # Conservative scaling: higher active symbols increases diversification but can amplify DD.
            # Apply soft score adjustments instead of rewriting live config directly.
            diversification_bonus = (msa - 2) * 0.02
            dd_penalty = min(m["max_drawdown"] / 20.0, 0.20)
            score = (
                0.45 * m["win_rate"]
                + 0.35 * min(m["profit_factor"] / 3.0, 1.0)
                + 0.20 * m["signal_success_rate"]
                + diversification_bonus
                - dd_penalty
            )

            row = {
                "MIN_EDGE_THRESHOLD": th,
                "MAX_SYMBOL_ACTIVE": msa,
                "POSITION_SIZE": "dynamic",
                "estimated_trade_count": m["trade_count"],
                "estimated_win_rate": round(m["win_rate"], 6),
                "estimated_profit_factor": round(m["profit_factor"], 6),
                "estimated_max_drawdown": round(m["max_drawdown"], 6),
                "estimated_signal_success_rate": round(m["signal_success_rate"], 6),
                "score": round(score, 6),
            }
            tested.append(row)
            if best is None or row["score"] > best["score"]:
                best = row

    if best is None:
        best = {
            "MIN_EDGE_THRESHOLD": 0.5,
            "MAX_SYMBOL_ACTIVE": 3,
            "POSITION_SIZE": "dynamic",
            "estimated_trade_count": 0,
            "estimated_win_rate": 0.0,
            "estimated_profit_factor": 0.0,
            "estimated_max_drawdown": 0.0,
            "estimated_signal_success_rate": 0.0,
            "score": 0.0,
        }

    best["HIGH_VOL_POLICY"] = "REDUCED_SIZE"
    best["optimization_window"] = "last_available_history"

    return {
        "search_space": {
            "MIN_EDGE_THRESHOLD": "0.4~0.7",
            "MAX_SYMBOL_ACTIVE": "2~5",
            "POSITION_SIZE": "dynamic",
        },
        "best": best,
        "tested_count": len(tested),
        "top5": sorted(tested, key=lambda x: x["score"], reverse=True)[:5],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_report_text(metrics: dict[str, Any], ranking: list[dict[str, Any]], opt: dict[str, Any], counters: dict[str, Any]) -> str:
    best_score = ranking[0]["strategy_score"] if ranking else 0.0
    best_id = ranking[0]["strategy_id"] if ranking else "none"
    best_regime = ranking[0]["market_regime"] if ranking else "none"

    return "\n".join(
        [
            "PHASE7_STRATEGY_PERFORMANCE_REPORT",
            f"GENERATED_AT_KST={datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"TRADE_COUNT={metrics['trade_count']}",
            f"SIGNAL_COUNT={counters['signal_count']}",
            f"ENTRY_COUNT={counters['entry_count']}",
            f"EXIT_COUNT={counters['exit_count']}",
            f"WIN_RATE={metrics['win_rate']:.6f}",
            f"PROFIT_FACTOR={metrics['profit_factor']:.6f}",
            f"AVERAGE_RISK_REWARD={metrics['average_risk_reward']:.6f}",
            f"MAX_DRAWDOWN={metrics['max_drawdown']:.6f}",
            f"SIGNAL_SUCCESS_RATE={metrics['signal_success_rate']:.6f}",
            f"NET_PNL={metrics['net_pnl']:.6f}",
            f"BEST_STRATEGY_ID={best_id}",
            f"BEST_STRATEGY_REGIME={best_regime}",
            f"BEST_STRATEGY_SCORE={best_score}",
            f"OPTIMIZED_MIN_EDGE_THRESHOLD={opt['best']['MIN_EDGE_THRESHOLD']}",
            f"OPTIMIZED_MAX_SYMBOL_ACTIVE={opt['best']['MAX_SYMBOL_ACTIVE']}",
            f"OPTIMIZED_POSITION_SIZE={opt['best']['POSITION_SIZE']}",
            f"OPTIMIZED_HIGH_VOL_POLICY={opt['best']['HIGH_VOL_POLICY']}",
            "DEPLOYMENT_MODE=SAFE_UPDATE_PLAN_ONLY",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE7 AI Strategy Evolution Engine")
    parser.add_argument(
        "--runtime-dir",
        default=r"C:\next-trade-ver1.0\logs\runtime",
        help="Runtime logs directory",
    )
    parser.add_argument(
        "--out-dir",
        default=r"C:\next-trade-ver1.0\reports\phase7_strategy",
        help="Output report directory",
    )
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    profitmax_path = runtime_dir / "profitmax_v1_events.jsonl"
    investor_path = runtime_dir / "investor_order_api.jsonl"
    multi5_path = runtime_dir / "multi5_runtime_events.jsonl"

    profitmax_events = read_jsonl(profitmax_path)
    investor_events = read_jsonl(investor_path)
    multi5_events = read_jsonl(multi5_path)

    trades, strategy_events, counters = build_trade_data(profitmax_events)

    # Enrich strategy events with multi5 edge history context (best-effort)
    if multi5_events:
        for ev in multi5_events[-500:]:
            strategy_events.append(
                {
                    "ts": ev.get("ts"),
                    "event_type": "MULTI5_RUNTIME_SNAPSHOT",
                    "symbol": ev.get("selected_symbol"),
                    "trace_id": None,
                    "strategy_id": "multi5_runtime",
                    "regime": "runtime",
                    "signal_score": safe_float(ev.get("edge_score")),
                    "expected_edge": safe_float(ev.get("edge_score")),
                    "engine_entry_attempted": bool(ev.get("engine_entry_attempted", False)),
                    "engine_running": bool(ev.get("engine_running", False)),
                }
            )

    trade_rows: list[dict[str, Any]] = []
    for t in trades:
        trade_rows.append(
            {
                "trace_id": t.trace_id,
                "symbol": t.symbol,
                "strategy_id": t.strategy_id,
                "market_regime": t.regime,
                "entry_ts": t.entry_ts.isoformat(),
                "exit_ts": t.exit_ts.isoformat(),
                "holding_time_sec": round(t.holding_sec, 3),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "qty": t.qty,
                "profit_loss": t.pnl,
                "entry_signal": {
                    "signal_score": t.entry_signal_score,
                    "expected_edge": t.entry_expected_edge,
                },
                "exit_reason": t.exit_reason,
            }
        )

    metrics = compute_metrics(trades, signal_count=counters["signal_count"])
    ranking = strategy_ranking(trades)
    optimization = optimize_params(trades, counters)

    # Files required by directive
    strategy_events_out = out_dir / "strategy_events.jsonl"
    trade_performance_out = out_dir / "trade_performance.jsonl"
    perf_report_out = out_dir / "strategy_performance_report.txt"
    ranking_out = out_dir / "strategy_ranking.json"
    optimized_out = out_dir / "optimized_strategy_parameters.json"

    write_jsonl(strategy_events_out, strategy_events)
    write_jsonl(trade_performance_out, trade_rows)
    perf_report_out.write_text(build_report_text(metrics, ranking, optimization, counters), encoding="utf-8")
    ranking_out.write_text(json.dumps(ranking, indent=2, ensure_ascii=False), encoding="utf-8")
    optimized_out.write_text(json.dumps(optimization, indent=2, ensure_ascii=False), encoding="utf-8")

    # Optional safe deployment plan (no direct live patch)
    deploy_plan = {
        "STRATEGY_UPDATE_TRIGGER": {
            "min_trades": 20,
            "min_profit_factor": 1.1,
            "max_drawdown": 5.0,
            "min_signal_success_rate": 0.2,
        },
        "SAFE_DEPLOY_PLAN": {
            "CONFIG_UPDATE": {
                "MIN_EDGE_THRESHOLD": optimization["best"]["MIN_EDGE_THRESHOLD"],
                "MAX_SYMBOL_ACTIVE": optimization["best"]["MAX_SYMBOL_ACTIVE"],
                "HIGH_VOL_POLICY": optimization["best"]["HIGH_VOL_POLICY"],
            },
            "ENGINE_RESTART_SAFE": "schedule_restart_via_BOOT_control_center_only",
            "AUTO_APPLY": False,
        },
    }
    (out_dir / "strategy_deploy_plan.json").write_text(
        json.dumps(deploy_plan, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Honey summary format requested
    honey_summary = "\n".join(
        [
            f"PHASE7_DATA_COLLECTION=YES",
            f"TRADE_COUNT={metrics['trade_count']}",
            f"WIN_RATE={metrics['win_rate']:.6f}",
            f"PROFIT_FACTOR={metrics['profit_factor']:.6f}",
            f"BEST_STRATEGY_SCORE={(ranking[0]['strategy_score'] if ranking else 0.0)}",
            f"OPTIMIZED_PARAMETERS={json.dumps(optimization['best'], ensure_ascii=False)}",
            f"SYSTEM_STATUS=PHASE7_ENGINE_BUILT_AND_ANALYZED",
            f"SOURCE_LOGS={{\"profitmax\":{len(profitmax_events)},\"investor\":{len(investor_events)},\"multi5\":{len(multi5_events)}}}",
        ]
    )
    (out_dir / "nt_phase7_honey_summary.txt").write_text(honey_summary, encoding="utf-8")

    print("PHASE7_STATUS=COMPLETE")
    print(f"OUTPUT_DIR={out_dir}")
    print(f"TRADE_COUNT={metrics['trade_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


