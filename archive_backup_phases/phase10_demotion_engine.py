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


def evaluate_demotion(lifecycle: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    # Thresholds (configurable defaults)
    consecutive_loss_limit = 3
    live_pf_floor = 0.8
    drawdown_breach_proxy = 70.0  # mapped from risk score
    data_staleness_limit_hours = 24
    now = datetime.now(KST)

    candidates: list[dict[str, Any]] = []
    for row in lifecycle:
        state = str(row.get("STATE", "DISCOVERED"))
        if state not in ("LIVE_CANDIDATE", "LIVE_ACTIVE", "SHADOW_READY", "PAPER_TESTING"):
            continue

        pf = fnum(row.get("profit_factor"))
        risk = fnum(row.get("RISK_SCORE"), 100.0)
        live_score = fnum(row.get("LIVE_SCORE"))
        # proxy loss-streak estimate
        loss_streak_proxy = 3 if (pf < 0.7 and risk > 60) else (2 if pf < 0.9 else 0)
        last_review_str = str(row.get("last_review_ts", ""))
        stale = False
        try:
            # Parse format "YYYY-MM-DD HH:MM:SS UTC+09:00" by slicing date-time only.
            dt = datetime.strptime(last_review_str[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
            stale = (now - dt).total_seconds() > data_staleness_limit_hours * 3600
        except Exception:
            stale = True

        decision = "HOLD"
        reasons: list[str] = []
        if loss_streak_proxy >= consecutive_loss_limit or pf < live_pf_floor or risk >= drawdown_breach_proxy or stale:
            if state in ("LIVE_ACTIVE", "LIVE_CANDIDATE"):
                decision = "DEMOTE_TO_SHADOW"
            else:
                decision = "RETIRE"

            if loss_streak_proxy >= consecutive_loss_limit:
                reasons.append("CONSECUTIVE_LOSS_LIMIT")
            if pf < live_pf_floor:
                reasons.append("LIVE_PROFIT_FACTOR_FLOOR")
            if risk >= drawdown_breach_proxy:
                reasons.append("DRAWDOWN_BREACH")
            if stale:
                reasons.append("DATA_STALENESS_LIMIT")

        candidates.append(
            {
                "ALPHA_ID": row.get("ALPHA_ID"),
                "CURRENT_STATE": state,
                "DECISION": decision,
                "LIVE_SCORE": round(live_score, 4),
                "RISK_SCORE": round(risk, 4),
                "profit_factor": round(pf, 6),
                "loss_streak_proxy": loss_streak_proxy,
                "reasons": reasons if reasons else ["within_limits"],
            }
        )

    report = "\n".join(
        [
            "PHASE10_RETIREMENT_REPORT",
            f"GENERATED_AT_KST={now.strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"CONSECUTIVE_LOSS_LIMIT={consecutive_loss_limit}",
            f"LIVE_PROFIT_FACTOR_FLOOR={live_pf_floor}",
            f"DRAWDOWN_BREACH_PROXY_RISK_SCORE={drawdown_breach_proxy}",
            f"DATA_STALENESS_LIMIT_HOURS={data_staleness_limit_hours}",
            f"TOTAL_REVIEWED={len(candidates)}",
            f"HOLD_COUNT={sum(1 for x in candidates if x.get('DECISION') == 'HOLD')}",
            f"DEMOTE_TO_SHADOW_COUNT={sum(1 for x in candidates if x.get('DECISION') == 'DEMOTE_TO_SHADOW')}",
            f"RETIRE_COUNT={sum(1 for x in candidates if x.get('DECISION') == 'RETIRE')}",
        ]
    )
    return candidates, report


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE10 Demotion/Retirement Engine")
    parser.add_argument("--lifecycle-registry", required=True)
    parser.add_argument("--out-candidates", required=True)
    parser.add_argument("--out-report", required=True)
    args = parser.parse_args()

    lifecycle = read_json(Path(args.lifecycle_registry), default=[])
    candidates, report = evaluate_demotion(lifecycle)
    Path(args.out_candidates).write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(args.out_report).write_text(report, encoding="utf-8")
    print("PHASE10_DEMOTION_STATUS=COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

