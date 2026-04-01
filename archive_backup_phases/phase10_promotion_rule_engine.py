from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))


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


def evaluate_promotion(
    lifecycle: list[dict[str, Any]],
    min_paper_trades: int = 30,
    min_shadow_trades: int = 20,
    min_pf: float = 1.2,
    max_drawdown_proxy: float = 55.0,
    min_stability: float = 60.0,
) -> tuple[list[dict[str, Any]], str]:
    candidates: list[dict[str, Any]] = []
    for row in lifecycle:
        state = str(row.get("STATE", "DISCOVERED"))
        trades = int(row.get("trade_sample_count", 0))
        pf = fnum(row.get("profit_factor"))
        live_score = fnum(row.get("LIVE_SCORE"))
        risk = fnum(row.get("RISK_SCORE"), 100.0)
        stability = max(0.0, live_score - 0.6 * risk)

        target_state = None
        eligible = False
        reasons: list[str] = []

        if state in ("DISCOVERED", "PAPER_TESTING"):
            target_state = "SHADOW_READY"
            if trades >= min_paper_trades and pf >= min_pf and risk <= max_drawdown_proxy and stability >= min_stability:
                eligible = True
            else:
                reasons.append("paper_threshold_not_met")
        elif state == "SHADOW_READY":
            target_state = "LIVE_CANDIDATE"
            if trades >= (min_paper_trades + min_shadow_trades) and pf >= min_pf and risk <= max_drawdown_proxy and stability >= min_stability:
                eligible = True
            else:
                reasons.append("shadow_threshold_not_met")

        if target_state:
            candidates.append(
                {
                    "ALPHA_ID": row.get("ALPHA_ID"),
                    "CURRENT_STATE": state,
                    "TARGET_STATE": target_state,
                    "ELIGIBLE": eligible,
                    "trade_sample_count": trades,
                    "profit_factor": round(pf, 6),
                    "LIVE_SCORE": round(live_score, 4),
                    "RISK_SCORE": round(risk, 4),
                    "STABILITY_SCORE": round(stability, 4),
                    "REASONS": reasons if reasons else ["eligible"],
                }
            )

    report = "\n".join(
        [
            "PHASE10_PROMOTION_REPORT",
            f"GENERATED_AT_KST={datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"MIN_PAPER_TRADES={min_paper_trades}",
            f"MIN_SHADOW_TRADES={min_shadow_trades}",
            f"MIN_PROFIT_FACTOR={min_pf}",
            f"MAX_DRAWDOWN_PROXY={max_drawdown_proxy}",
            f"MIN_STABILITY_SCORE={min_stability}",
            f"TOTAL_REVIEWED={len(candidates)}",
            f"ELIGIBLE_COUNT={sum(1 for c in candidates if c.get('ELIGIBLE'))}",
            f"INELIGIBLE_COUNT={sum(1 for c in candidates if not c.get('ELIGIBLE'))}",
        ]
    )
    return candidates, report


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE10 Promotion Rule Engine")
    parser.add_argument("--lifecycle-registry", required=True)
    parser.add_argument("--out-candidates", required=True)
    parser.add_argument("--out-report", required=True)
    args = parser.parse_args()

    lifecycle = read_json(Path(args.lifecycle_registry), default=[])
    candidates, report = evaluate_promotion(lifecycle)
    Path(args.out_candidates).write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.out_report).write_text(report, encoding="utf-8")
    print("PHASE10_PROMOTION_RULE_STATUS=COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

