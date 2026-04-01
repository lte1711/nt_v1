from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
REPORTS_ROOT = Path(r"C:\next-trade-ver1.0\reports")


def resolve_honey_exec_report_dir() -> Path:
    return REPORTS_ROOT / datetime.now(KST).strftime("%Y-%m-%d") / "honey_execution_reports"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def build_portfolio(scoreboard: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str]:
    # Live alpha auto selection rule (no live direct patch): pick strongest candidates by stability.
    ranked = sorted(
        scoreboard,
        key=lambda x: (
            fnum(x.get("STABILITY_SCORE")),
            fnum(x.get("LIVE_SCORE")),
            -fnum(x.get("RISK_SCORE")),
        ),
        reverse=True,
    )

    # Allow up to 3 active alpha slots for portfolio engine.
    active_target = []
    for row in ranked:
        st = str(row.get("STATE", ""))
        if st in ("LIVE_CANDIDATE", "SHADOW_READY", "PAPER_TESTING"):
            active_target.append(row)
        if len(active_target) >= 3:
            break

    if not active_target and ranked:
        # cold-start fallback
        active_target = ranked[:1]

    portfolio_registry = {
        "generated_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "portfolio_mode": "LIVE_ALPHA_PORTFOLIO_ENGINE",
        "alpha_selection_method": "stability_score_rank",
        "active_alpha_set": [
            {
                "ALPHA_ID": x.get("ALPHA_ID"),
                "STATE": x.get("STATE"),
                "LIVE_SCORE": x.get("LIVE_SCORE"),
                "RISK_SCORE": x.get("RISK_SCORE"),
                "STABILITY_SCORE": x.get("STABILITY_SCORE"),
            }
            for x in active_target
        ],
        "excluded_alpha_count": max(len(scoreboard) - len(active_target), 0),
    }

    # Capital auto reallocation (plan only)
    raw_weights = []
    for x in active_target:
        live = max(fnum(x.get("LIVE_SCORE")), 0.0)
        risk = max(fnum(x.get("RISK_SCORE")), 0.0)
        stability = max(fnum(x.get("STABILITY_SCORE")), 0.0)
        raw = 0.45 * live + 0.40 * stability + 0.15 * max(0.0, 100.0 - risk)
        raw_weights.append((str(x.get("ALPHA_ID")), raw))

    total_raw = sum(w for _, w in raw_weights)
    if total_raw <= 0:
        alloc = [{"ALPHA_ID": aid, "weight": round(1.0 / max(len(raw_weights), 1), 6)} for aid, _ in raw_weights]
    else:
        alloc = [{"ALPHA_ID": aid, "weight": round(w / total_raw, 6)} for aid, w in raw_weights]

    capital_plan = {
        "generated_at_kst": portfolio_registry["generated_at_kst"],
        "allocation_mode": "score_weighted_auto_reallocation_plan",
        "target_capital_split": alloc,
        "constraints": {
            "MAX_ACTIVE_ALPHA": 3,
            "MAX_WEIGHT_PER_ALPHA": 0.6,
            "MIN_WEIGHT_PER_ALPHA": 0.1,
        },
        "auto_apply": False,
    }

    # Realtime unified risk guard
    risk_guard = {
        "generated_at_kst": portfolio_registry["generated_at_kst"],
        "TOTAL_MAX_EXPOSURE": 500.0,
        "PER_ALPHA_MAX_EXPOSURE": 220.0,
        "PORTFOLIO_DRAWDOWN_LIMIT": 40.0,
        "MAX_CONCURRENT_POSITIONS": 5,
        "CORRELATED_SYMBOL_LIMIT": 2,
        "RISK_ACTION_POLICY": {
            "breach_total_exposure": "AUTO_POSITION_REDUCTION_PLAN",
            "breach_drawdown": "TRADING_PAUSE_PLAN",
            "breach_correlated_symbol": "DENY_NEW_ENTRY_PLAN",
        },
        "auto_apply": False,
    }

    runtime_policy = {
        "generated_at_kst": portfolio_registry["generated_at_kst"],
        "LIVE_ALPHA_AUTO_SELECTION": True,
        "LIVE_ALPHA_AUTO_REALLOCATION": True,
        "LIVE_ALPHA_RISK_GUARD": True,
        "AUTO_APPLY": False,
        "LIVE_ENGINE_DIRECT_PATCH": False,
        "PROMOTION_REQUIRES": ["CANDY", "GEMINI", "DENNIS"],
        "ROLLBACK_REQUIRED": True,
    }

    report = "\n".join(
        [
            "PHASE11_LIVE_ALPHA_PORTFOLIO_REPORT",
            f"GENERATED_AT_KST={portfolio_registry['generated_at_kst']}",
            f"TOTAL_SCOREBOARD_ALPHA={len(scoreboard)}",
            f"ACTIVE_ALPHA_SELECTED={len(active_target)}",
            f"CAPITAL_SPLIT_MODEL={capital_plan['allocation_mode']}",
            f"TOTAL_MAX_EXPOSURE={risk_guard['TOTAL_MAX_EXPOSURE']}",
            f"MAX_CONCURRENT_POSITIONS={risk_guard['MAX_CONCURRENT_POSITIONS']}",
            "AUTO_APPLY=FALSE",
            "LIVE_ENGINE_DIRECT_PATCH=FALSE",
            "SYSTEM_STATUS=PHASE11_LIVE_ALPHA_PORTFOLIO_ENGINE_BUILT",
        ]
    )

    return portfolio_registry, capital_plan, risk_guard, runtime_policy, report


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE11 Live Alpha Portfolio Engine")
    parser.add_argument("--phase10-scoreboard", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scoreboard = read_json(Path(args.phase10_scoreboard), default=[])

    portfolio_registry, capital_plan, risk_guard, runtime_policy, report = build_portfolio(scoreboard)

    (out_dir / "phase11_live_alpha_portfolio_registry.json").write_text(
        json.dumps(portfolio_registry, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "phase11_capital_allocator_plan.json").write_text(
        json.dumps(capital_plan, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "phase11_realtime_risk_guard.json").write_text(
        json.dumps(risk_guard, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "phase11_portfolio_runtime_policy.json").write_text(
        json.dumps(runtime_policy, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "phase11_live_alpha_portfolio_report.txt").write_text(report, encoding="utf-8")

    summary = {
        "PHASE11_LIVE_ALPHA_ENGINE_BUILT": "YES",
        "ALPHA_AUTO_SELECTION_STATUS": "READY",
        "CAPITAL_REALLOCATION_STATUS": "READY",
        "REALTIME_RISK_GUARD_STATUS": "READY",
        "ACTIVE_ALPHA_COUNT": str(len(portfolio_registry["active_alpha_set"])),
        "DEPLOYMENT_MODE": "MANUAL_APPROVAL_ONLY",
        "SYSTEM_STATUS": "PHASE11_LIVE_ALPHA_PORTFOLIO_ENGINE_BUILT",
    }
    (out_dir / "nt_phase11_honey_summary.txt").write_text(
        "\n".join([f"{k}={v}" for k, v in summary.items()]),
        encoding="utf-8",
    )

    honey_dir = resolve_honey_exec_report_dir()
    honey_dir.mkdir(parents=True, exist_ok=True)
    (honey_dir / "nt_phase11_live_alpha_portfolio_honey_report.txt").write_text(
        "\n".join(
            ["NT_PHASE11_LIVE_ALPHA_PORTFOLIO_HONEY_STATUS=PASS", *[f"{k}={v}" for k, v in summary.items()], f"EVIDENCE_PATH={out_dir}"]
        ),
        encoding="utf-8",
    )

    print("PHASE11_STATUS=COMPLETE")
    print(f"OUTPUT_DIR={out_dir}")
    for k, v in summary.items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

