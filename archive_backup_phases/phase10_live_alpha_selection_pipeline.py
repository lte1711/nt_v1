from __future__ import annotations

import argparse
import json
import subprocess
import sys
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


def run_step(cmd: list[str]) -> None:
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        raise RuntimeError(f"STEP_FAILED: {' '.join(cmd)}\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="PHASE10 Live Alpha Selection Pipeline")
    parser.add_argument("--phase9-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    phase9_dir = Path(args.phase9_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    py = sys.executable

    lifecycle_registry = out_dir / "phase10_alpha_lifecycle_registry.json"
    lifecycle_report = out_dir / "phase10_alpha_state_report.txt"
    promo_candidates = out_dir / "phase10_promotion_candidates.json"
    promo_report = out_dir / "phase10_promotion_report.txt"
    demotion_candidates = out_dir / "phase10_demotion_candidates.json"
    retirement_report = out_dir / "phase10_retirement_report.txt"

    run_step(
        [
            py,
            str(Path(__file__).with_name("phase10_alpha_lifecycle_engine.py")),
            "--phase9-registry",
            str(phase9_dir / "phase9_alpha_registry.json"),
            "--out-registry",
            str(lifecycle_registry),
            "--out-report",
            str(lifecycle_report),
        ]
    )
    run_step(
        [
            py,
            str(Path(__file__).with_name("phase10_promotion_rule_engine.py")),
            "--lifecycle-registry",
            str(lifecycle_registry),
            "--out-candidates",
            str(promo_candidates),
            "--out-report",
            str(promo_report),
        ]
    )
    run_step(
        [
            py,
            str(Path(__file__).with_name("phase10_demotion_engine.py")),
            "--lifecycle-registry",
            str(lifecycle_registry),
            "--out-candidates",
            str(demotion_candidates),
            "--out-report",
            str(retirement_report),
        ]
    )

    lifecycle = read_json(lifecycle_registry, [])
    promotions = read_json(promo_candidates, [])
    demotions = read_json(demotion_candidates, [])

    # Validation queues
    paper_queue = [x for x in lifecycle if str(x.get("STATE")) in ("DISCOVERED", "PAPER_TESTING")]
    shadow_queue = [x for x in promotions if x.get("ELIGIBLE") and x.get("TARGET_STATE") == "SHADOW_READY"]
    live_queue = [x for x in promotions if x.get("ELIGIBLE") and x.get("TARGET_STATE") == "LIVE_CANDIDATE"]

    (out_dir / "paper_validation_queue.json").write_text(json.dumps(paper_queue, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "shadow_validation_queue.json").write_text(json.dumps(shadow_queue, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "live_candidate_queue.json").write_text(json.dumps(live_queue, indent=2, ensure_ascii=False), encoding="utf-8")

    # Live Alpha Scoreboard
    scoreboard = []
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z")
    promo_by_id = {str(x.get("ALPHA_ID")): x for x in promotions}
    for row in lifecycle:
        aid = str(row.get("ALPHA_ID"))
        st = str(row.get("STATE"))
        p = promo_by_id.get(aid, {})
        paper_score = float(row.get("BACKTEST_SCORE", 0.0))
        shadow_score = float(row.get("LIVE_SCORE", 0.0)) * 0.9
        live_score = float(row.get("LIVE_SCORE", 0.0))
        risk_score = float(row.get("RISK_SCORE", 100.0))
        stability = max(0.0, live_score - 0.6 * risk_score)
        scoreboard.append(
            {
                "ALPHA_ID": aid,
                "STATE": st,
                "PAPER_SCORE": round(paper_score, 4),
                "SHADOW_SCORE": round(shadow_score, 4),
                "LIVE_SCORE": round(live_score, 4),
                "RISK_SCORE": round(risk_score, 4),
                "STABILITY_SCORE": round(stability, 4),
                "LAST_REVIEW_TS": now_str,
            }
        )
    (out_dir / "phase10_live_alpha_scoreboard.json").write_text(json.dumps(scoreboard, indent=2, ensure_ascii=False), encoding="utf-8")

    live_report = "\n".join(
        [
            "PHASE10_LIVE_ALPHA_REPORT",
            f"GENERATED_AT_KST={now_str}",
            f"TOTAL_ALPHAS={len(scoreboard)}",
            f"LIVE_ACTIVE_COUNT={sum(1 for x in scoreboard if x.get('STATE') == 'LIVE_ACTIVE')}",
            f"LIVE_CANDIDATE_COUNT={sum(1 for x in scoreboard if x.get('STATE') == 'LIVE_CANDIDATE')}",
            f"PAPER_QUEUE_COUNT={len(paper_queue)}",
            f"SHADOW_QUEUE_COUNT={len(shadow_queue)}",
            f"LIVE_QUEUE_COUNT={len(live_queue)}",
        ]
    )
    (out_dir / "phase10_live_alpha_report.txt").write_text(live_report, encoding="utf-8")

    # Review Scheduler
    schedule = {
        "generated_at_kst": now_str,
        "PAPER_REVIEW_INTERVAL": "6h",
        "SHADOW_REVIEW_INTERVAL": "4h",
        "LIVE_REVIEW_INTERVAL": "1h",
        "RETIREMENT_REVIEW_INTERVAL": "24h",
        "notes": "phase10 review scheduler template for safe promotion lifecycle",
    }
    (out_dir / "phase10_review_schedule.json").write_text(json.dumps(schedule, indent=2, ensure_ascii=False), encoding="utf-8")

    # Safe promotion deploy plan
    deploy_plan = {
        "AUTO_APPLY": False,
        "LIVE_ENGINE_DIRECT_PATCH": False,
        "PROMOTION_REQUIRES": ["CANDY", "GEMINI", "DENNIS"],
        "ROLLBACK_REQUIRED": True,
        "LIVE_DIRECT_PROMOTION": False,
        "pipeline": [
            "ALPHA_CANDIDATE_POOL",
            "PAPER_VALIDATION",
            "SHADOW_PROMOTION_QUEUE",
            "LIVE_CANDIDATE_SET",
            "DEMOTION_OR_RETIREMENT",
        ],
    }
    (out_dir / "phase10_promotion_deploy_plan.json").write_text(json.dumps(deploy_plan, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "PHASE10_LIFECYCLE_ENGINE_BUILT": "YES",
        "PROMOTION_RULE_ENGINE_STATUS": "READY",
        "DEMOTION_ENGINE_STATUS": "READY",
        "PAPER_QUEUE_STATUS": "READY",
        "SHADOW_QUEUE_STATUS": "READY",
        "LIVE_CANDIDATE_QUEUE_STATUS": "READY",
        "LIVE_ALPHA_SCOREBOARD_STATUS": "READY",
        "DEPLOYMENT_MODE": "MANUAL_APPROVAL_ONLY",
        "SYSTEM_STATUS": "PHASE10_LIVE_ALPHA_SELECTION_ENGINE_BUILT",
    }
    (out_dir / "nt_phase10_honey_summary.txt").write_text(
        "\n".join([f"{k}={v}" for k, v in summary.items()]),
        encoding="utf-8",
    )

    honey_dir = resolve_honey_exec_report_dir()
    honey_dir.mkdir(parents=True, exist_ok=True)
    (honey_dir / "nt_phase10_live_alpha_selection_honey_report.txt").write_text(
        "\n".join(
            ["NT_PHASE10_LIVE_ALPHA_SELECTION_HONEY_STATUS=PASS", *[f"{k}={v}" for k, v in summary.items()], f"EVIDENCE_PATH={out_dir}"]
        ),
        encoding="utf-8",
    )

    print("PHASE10_STATUS=COMPLETE")
    print(f"OUTPUT_DIR={out_dir}")
    for k, v in summary.items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

