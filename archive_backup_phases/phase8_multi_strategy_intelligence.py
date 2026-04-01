from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any

KST = timezone(timedelta(hours=9))
REPORTS_ROOT = Path(r"C:\next-trade-ver1.0\reports")


def resolve_honey_exec_report_dir() -> Path:
    return REPORTS_ROOT / datetime.now(KST).strftime("%Y-%m-%d") / "honey_execution_reports"


@dataclass
class StrategyStat:
    strategy_name: str
    trade_count: int
    win_rate: float
    profit_factor: float
    avg_holding_time: float
    max_drawdown: float
    recent_score: float
    net_pnl: float


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


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


def drawdown_from_pnls(pnls: list[float]) -> float:
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in pnls:
        eq += x
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > max_dd:
            max_dd = dd
    return max_dd


def recent_score_from_pnls(pnls: list[float]) -> float:
    if not pnls:
        return 0.0
    recent = pnls[-5:]
    win_ratio = sum(1 for x in recent if x > 0) / len(recent)
    avg = mean(recent)
    dd = drawdown_from_pnls(recent)
    # 0~100 near-normalized operational score
    score = 100.0 * (0.50 * win_ratio + 0.35 * max(min(avg / 1.0, 1.0), -1.0) * 0.5 + 0.15 * (1.0 - min(dd / 2.0, 1.0)))
    return max(0.0, round(score, 4))


def compute_stat(strategy_name: str, trades: list[dict[str, Any]]) -> StrategyStat:
    tc = len(trades)
    pnls = [safe_float(t.get("profit_loss")) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = (len(wins) / tc) if tc else 0.0
    gross_profit = sum(wins)
    gross_loss_abs = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss_abs) if gross_loss_abs > 0 else (999.0 if gross_profit > 0 else 0.0)
    avg_holding = mean([safe_float(t.get("holding_time_sec")) for t in trades]) if trades else 0.0
    max_dd = drawdown_from_pnls(pnls)
    recent_score = recent_score_from_pnls(pnls)
    net_pnl = sum(pnls)
    return StrategyStat(
        strategy_name=strategy_name,
        trade_count=tc,
        win_rate=win_rate,
        profit_factor=profit_factor,
        avg_holding_time=avg_holding,
        max_drawdown=max_dd,
        recent_score=recent_score,
        net_pnl=net_pnl,
    )


def build_phase8(
    trade_rows: list[dict[str, Any]],
    phase7_ranking: list[dict[str, Any]],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
    str,
    dict[str, Any],
    str,
    dict[str, Any],
    dict[str, Any],
]:
    # Alpha factory slots (PHASE8 dedicated registry)
    alpha_slots = {
        "TREND_STRATEGY": {
            "strategy_filters": {"strategy_id": ["trend_scalp", "trend"], "market_regime": ["trend"]},
            "enabled": True,
        },
        "RANGE_STRATEGY": {
            "strategy_filters": {"strategy_id": ["range_scalp", "range"], "market_regime": ["range"]},
            "enabled": True,
        },
        "BREAKOUT_STRATEGY": {
            "strategy_filters": {"strategy_id": ["breakout_scalp", "breakout"], "market_regime": ["breakout"]},
            "enabled": True,
        },
        "MEAN_REVERSION_STRATEGY": {
            "strategy_filters": {"strategy_id": ["mean_reversion", "mean_reversion_scalp"], "market_regime": ["mean_reversion", "range"]},
            "enabled": True,
        },
    }

    def match(slot: dict[str, Any], tr: dict[str, Any]) -> bool:
        sid = str(tr.get("strategy_id", ""))
        regime = str(tr.get("market_regime", ""))
        sids = slot["strategy_filters"]["strategy_id"]
        regimes = slot["strategy_filters"]["market_regime"]
        return sid in sids or regime in regimes

    slot_trades: dict[str, list[dict[str, Any]]] = {k: [] for k in alpha_slots}

    def classify_trade(tr: dict[str, Any]) -> str:
        sid = str(tr.get("strategy_id", "")).lower()
        regime = str(tr.get("market_regime", "")).lower()
        if "trend" in sid or regime == "trend":
            return "TREND_STRATEGY"
        if "breakout" in sid or regime == "breakout":
            return "BREAKOUT_STRATEGY"
        if "mean_reversion" in sid or regime == "mean_reversion":
            return "MEAN_REVERSION_STRATEGY"
        if "range" in sid or regime == "range":
            return "RANGE_STRATEGY"
        return "RANGE_STRATEGY"

    for t in trade_rows:
        slot_trades[classify_trade(t)].append(t)

    stats: list[StrategyStat] = []
    for slot_name in alpha_slots:
        stats.append(compute_stat(slot_name, slot_trades[slot_name]))

    scoreboard: list[dict[str, Any]] = []
    for st in stats:
        scoreboard.append(
            {
                "STRATEGY_NAME": st.strategy_name,
                "TRADE_COUNT": st.trade_count,
                "WIN_RATE": round(st.win_rate, 6),
                "PROFIT_FACTOR": round(st.profit_factor, 6),
                "AVG_HOLDING_TIME": round(st.avg_holding_time, 3),
                "MAX_DRAWDOWN": round(st.max_drawdown, 6),
                "RECENT_SCORE": round(st.recent_score, 4),
                "NET_PNL": round(st.net_pnl, 6),
            }
        )

    # Meta-scheduler weights and active/disabled sets
    weight_rows: list[dict[str, Any]] = []
    for row in scoreboard:
        trade_count = int(row["TRADE_COUNT"])
        pf = float(row["PROFIT_FACTOR"])
        win = float(row["WIN_RATE"])
        dd = float(row["MAX_DRAWDOWN"])
        recent = float(row["RECENT_SCORE"])

        disabled = False
        if trade_count == 0:
            disabled = True
        elif trade_count >= 5 and win < 0.25 and pf < 0.7:
            disabled = True

        base_score = 0.0
        if not disabled:
            base_score = (
                0.30 * min(pf / 2.0, 1.0)
                + 0.30 * win
                + 0.25 * min(recent / 100.0, 1.0)
                + 0.15 * (1.0 - min(dd / 5.0, 1.0))
            )
        weight_rows.append(
            {
                "strategy": row["STRATEGY_NAME"],
                "raw_score": round(base_score, 6),
                "disabled": disabled,
            }
        )

    active = [x for x in weight_rows if not x["disabled"] and x["raw_score"] > 0]
    disabled_set = [x["strategy"] for x in weight_rows if x["disabled"]]

    if not active:
        # cold start fallback
        active_names = [x["strategy"] for x in weight_rows]
        ratio = round(1.0 / max(len(active_names), 1), 6)
        plan_items = [{"strategy": n, "weight": ratio} for n in active_names]
    else:
        total_raw = sum(x["raw_score"] for x in active)
        plan_items = [{"strategy": x["strategy"], "weight": round(x["raw_score"] / total_raw, 6)} for x in active]
        active_names = [x["strategy"] for x in active]

    meta_plan = {
        "generated_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "STRATEGY_WEIGHT": plan_items,
        "CAPITAL_ALLOCATION_RATIO": plan_items,
        "ACTIVE_STRATEGY_SET": active_names,
        "DISABLED_STRATEGY_SET": disabled_set,
        "policy": {
            "upweight_recent_outperformers": True,
            "downweight_loss_streak": True,
            "auto_disable_low_score_candidates": True,
        },
    }

    # Unified risk guard matrix
    total_max_exposure = 500.0
    max_concurrent_strategies = 3
    correlated_symbol_limit = 2

    risk_rows: list[dict[str, Any]] = []
    for w in plan_items:
        risk_rows.append(
            {
                "strategy": w["strategy"],
                "PER_STRATEGY_MAX_EXPOSURE": round(total_max_exposure * float(w["weight"]) * 0.9, 2),
                "allocation_ratio": w["weight"],
            }
        )

    risk_matrix = {
        "TOTAL_MAX_EXPOSURE": total_max_exposure,
        "CORRELATED_SYMBOL_LIMIT": correlated_symbol_limit,
        "MAX_CONCURRENT_STRATEGIES": max_concurrent_strategies,
        "strategy_limits": risk_rows,
    }

    risk_report = "\n".join(
        [
            "UNIFIED_RISK_GUARD_REPORT",
            f"GENERATED_AT_KST={datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"TOTAL_MAX_EXPOSURE={total_max_exposure}",
            f"CORRELATED_SYMBOL_LIMIT={correlated_symbol_limit}",
            f"MAX_CONCURRENT_STRATEGIES={max_concurrent_strategies}",
            f"ACTIVE_STRATEGY_SET={','.join(active_names)}",
            f"DISABLED_STRATEGY_SET={','.join(disabled_set) if disabled_set else 'NONE'}",
        ]
    )

    # Capital reallocation simulation
    pnl_map = {x["STRATEGY_NAME"]: float(x["NET_PNL"]) for x in scoreboard}
    dd_map = {x["STRATEGY_NAME"]: float(x["MAX_DRAWDOWN"]) for x in scoreboard}

    baseline_single = {
        "model": "BASELINE_SINGLE_STRATEGY_RESULT",
        "strategy": phase7_ranking[0]["strategy_id"] if phase7_ranking else "unknown",
        "net_pnl": float(phase7_ranking[0]["net_pnl"]) if phase7_ranking else 0.0,
        "max_drawdown": float(phase7_ranking[0]["max_drawdown"]) if phase7_ranking else 0.0,
    }

    # Build two required models + score-weight
    active_for_sim = active_names if active_names else [x["STRATEGY_NAME"] for x in scoreboard]
    top3 = active_for_sim[:3] if len(active_for_sim) >= 3 else active_for_sim

    model_203050_alloc = {}
    if len(top3) == 3:
        model_203050_alloc = {top3[0]: 0.2, top3[1]: 0.3, top3[2]: 0.5}
    elif len(top3) == 2:
        model_203050_alloc = {top3[0]: 0.4, top3[1]: 0.6}
    elif len(top3) == 1:
        model_203050_alloc = {top3[0]: 1.0}

    eq_weight = 1.0 / max(len(active_for_sim), 1)
    model_equal_alloc = {s: eq_weight for s in active_for_sim}
    model_score_alloc = {x["strategy"]: x["weight"] for x in plan_items}

    def simulate(model_name: str, alloc: dict[str, float]) -> dict[str, Any]:
        pnl = 0.0
        dd = 0.0
        concentration = 0.0
        if alloc:
            concentration = max(alloc.values())
        for s, w in alloc.items():
            pnl += pnl_map.get(s, 0.0) * w
            dd += dd_map.get(s, 0.0) * w
        dd *= (1.0 + max(concentration - 0.5, 0.0))
        stability = pnl - 0.30 * dd
        return {
            "model": model_name,
            "allocation": alloc,
            "projected_pnl": round(pnl, 6),
            "projected_max_drawdown": round(dd, 6),
            "stability_score": round(stability, 6),
        }

    models = [
        simulate("CAPITAL_SPLIT_20_30_50", model_203050_alloc),
        simulate("CAPITAL_SPLIT_EQUAL_WEIGHT", model_equal_alloc),
        simulate("CAPITAL_SPLIT_SCORE_WEIGHT", model_score_alloc),
    ]
    best_model = max(models, key=lambda x: x["stability_score"]) if models else {"model": "NONE"}

    cap_sim = {
        "BASELINE_SINGLE_STRATEGY_RESULT": baseline_single,
        "MULTI_STRATEGY_SIMULATED_RESULT": models,
        "BEST_CAPITAL_MODEL": best_model,
    }

    cap_report = "\n".join(
        [
            "CAPITAL_REALLOCATION_REPORT",
            f"GENERATED_AT_KST={datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"BASELINE_STRATEGY={baseline_single['strategy']}",
            f"BASELINE_NET_PNL={baseline_single['net_pnl']}",
            f"BEST_CAPITAL_MODEL={best_model.get('model', 'NONE')}",
            f"BEST_MODEL_STABILITY_SCORE={best_model.get('stability_score', 0)}",
            f"BEST_MODEL_PROJECTED_PNL={best_model.get('projected_pnl', 0)}",
            f"BEST_MODEL_PROJECTED_MAX_DRAWDOWN={best_model.get('projected_max_drawdown', 0)}",
        ]
    )

    registry = {
        "generated_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "strategies": alpha_slots,
        "notes": "PHASE8 additive-only multi-strategy slots. LIVE engine direct patch disabled.",
    }

    scoreboard_report = "\n".join(
        [
            "STRATEGY_SCOREBOARD_REPORT",
            f"GENERATED_AT_KST={datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        ]
        + [
            f"{x['STRATEGY_NAME']}: TRADE_COUNT={x['TRADE_COUNT']}, WIN_RATE={x['WIN_RATE']}, PROFIT_FACTOR={x['PROFIT_FACTOR']}, MAX_DRAWDOWN={x['MAX_DRAWDOWN']}, RECENT_SCORE={x['RECENT_SCORE']}"
            for x in scoreboard
        ]
    )

    deploy_plan = {
        "AUTO_APPLY": False,
        "LIVE_ENGINE_DIRECT_PATCH": False,
        "CONFIG_CANDIDATE_ONLY": True,
        "ROLLBACK_PLAN_REQUIRED": True,
        "manual_approval_required_by": ["CANDY", "GEMINI", "DENNIS"],
        "candidate_config": {
            "MIN_EDGE_THRESHOLD": 0.65,
            "MAX_SYMBOL_ACTIVE": 5,
            "HIGH_VOL_POLICY": "REDUCED_SIZE",
        },
        "safe_update_sequence": [
            "1) Create backup",
            "2) Apply candidate config in staging",
            "3) Observe 30m",
            "4) Approve by Dennis",
            "5) Apply via BOOT control center only",
        ],
    }

    honey_summary = {
        "PHASE8_ALPHA_FACTORY_BUILT": "YES",
        "STRATEGY_COUNT": str(len(alpha_slots)),
        "SCOREBOARD_STATUS": "READY",
        "META_SCHEDULER_STATUS": "READY",
        "UNIFIED_RISK_GUARD_STATUS": "READY",
        "BEST_CAPITAL_MODEL": best_model.get("model", "NONE"),
        "DEPLOYMENT_MODE": "MANUAL_APPROVAL_ONLY",
        "SYSTEM_STATUS": "PHASE8_MULTI_STRATEGY_INTELLIGENCE_BUILT",
    }

    return (
        registry,
        scoreboard,
        meta_plan,
        risk_matrix,
        risk_report,
        cap_sim,
        cap_report,
        deploy_plan,
        honey_summary,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE8 Multi-Strategy Intelligence Builder")
    parser.add_argument(
        "--phase7-dir",
        default=r"C:\next-trade-ver1.0\reports\phase7_strategy",
    )
    parser.add_argument(
        "--out-dir",
        default=r"C:\next-trade-ver1.0\reports\phase8_multi_strategy",
    )
    args = parser.parse_args()

    phase7_dir = Path(args.phase7_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    trade_rows = read_jsonl(phase7_dir / "trade_performance.jsonl")
    phase7_ranking = read_json(phase7_dir / "strategy_ranking.json", default=[])

    (
        registry,
        scoreboard,
        meta_plan,
        risk_matrix,
        risk_report,
        cap_sim,
        cap_report,
        deploy_plan,
        honey_summary,
    ) = build_phase8(trade_rows, phase7_ranking)

    # Required outputs
    (out_dir / "phase8_strategy_registry.json").write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "strategy_scoreboard.json").write_text(json.dumps(scoreboard, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "strategy_scoreboard_report.txt").write_text(scoreboard_report := "\n".join([
        "STRATEGY_SCOREBOARD_REPORT",
        f"GENERATED_AT_KST={datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        *[
            f"{x['STRATEGY_NAME']}: TRADE_COUNT={x['TRADE_COUNT']}, WIN_RATE={x['WIN_RATE']}, PROFIT_FACTOR={x['PROFIT_FACTOR']}, AVG_HOLDING_TIME={x['AVG_HOLDING_TIME']}, MAX_DRAWDOWN={x['MAX_DRAWDOWN']}, RECENT_SCORE={x['RECENT_SCORE']}"
            for x in scoreboard
        ],
    ]), encoding="utf-8")
    (out_dir / "meta_scheduler_plan.json").write_text(json.dumps(meta_plan, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "phase8_risk_matrix.json").write_text(json.dumps(risk_matrix, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "unified_risk_guard_report.txt").write_text(risk_report, encoding="utf-8")
    (out_dir / "capital_reallocation_simulation.json").write_text(json.dumps(cap_sim, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "capital_reallocation_report.txt").write_text(cap_report, encoding="utf-8")
    (out_dir / "phase8_deploy_plan.json").write_text(json.dumps(deploy_plan, indent=2, ensure_ascii=False), encoding="utf-8")

    summary_text = "\n".join([f"{k}={v}" for k, v in honey_summary.items()])
    (out_dir / "nt_phase8_honey_summary.txt").write_text(summary_text, encoding="utf-8")

    # Optional Honey execution report for governance
    honey_exec_report_dir = resolve_honey_exec_report_dir()
    honey_exec_report_dir.mkdir(parents=True, exist_ok=True)
    (honey_exec_report_dir / "nt_phase8_multi_strategy_honey_report.txt").write_text(
        "\n".join(
            [
                "NT_PHASE8_MULTI_STRATEGY_HONEY_STATUS=PASS",
                summary_text,
                f"EVIDENCE_PATH={out_dir}",
            ]
        ),
        encoding="utf-8",
    )

    print("PHASE8_STATUS=COMPLETE")
    print(f"OUTPUT_DIR={out_dir}")
    print(summary_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

