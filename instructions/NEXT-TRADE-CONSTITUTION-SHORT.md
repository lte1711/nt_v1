# NEXT-TRADE CONSTITUTION SHORT v1.2.1

```text
STATUS=ACTIVE
VERSION=1.2.1
UPDATED=2026-03-29
FILE=C:\nt_v1\instructions\NEXT-TRADE-CONSTITUTION-SHORT.md

PROJECT_ROOT=C:\nt_v1
BOOT_ROOT=C:\nt_v1\BOOT
ENGINE_ENTRY=C:\nt_v1\BOOT\start_engine.ps1
SRC_ROOT=C:\nt_v1\src
TOOLS_ROOT=C:\nt_v1\tools
LOG_ROOT=C:\nt_v1\logs
REPORT_ROOT=C:\nt_v1\reports
LEGACY_ROOT=C:\projects

VERIFY_FIRST=ACTIVE
BOOT_PRIORITY=ACTIVE
STEP_BY_STEP=ACTIVE
FACT_ONLY=ACTIVE
ASSUMPTION_LABELING=ACTIVE
EVIDENCE_REQUIRED=ACTIVE
WORKFLOW=BAEKSEOL->CODEX->CANDY->GEMINI->DENNIS
BASE_MODE=FACT_ONLY

ROLES=DENNIS:approval;BAEKSEOL:design;CODEX:execution;CANDY:data_validation;GEMINI:technical_verification;SUGAR:audit

KPI_STANDARD=SNAPSHOT
KPI_SOURCE=portfolio_metrics_snapshot.json
KPI_REBUILT_FROM=profitmax_v1_events.jsonl
KPI_FIELDS=total_trades|realized_pnl|win_rate|drawdown
RUNTIME_STATS=REFERENCE_ONLY
KPI_CHAIN=snapshot->api->dashboard

RULES=read_before_execution|project_root_only|block_legacy_runtime|preserve_boot_chain|one_member_one_step_then_report|use_FACT_INFERENCE_ASSUMPTION_UNKNOWN

PROHIBITIONS=non_codex_execution|candy_runtime_intervention|no_judgment_without_evidence|no_cross_strategy_state_sharing|no_runtime_kpi_mix

EVIDENCE=logs|files|api_responses|direct_measurements
FACT=verified
INFERENCE=minimal
ASSUMPTION=labeled
UNKNOWN=not_confirmed
```

```text
LATEST_AUDITED_SESSION_DATE=2026-03-29
LATEST_AUDITED_SESSION_GRADE=PASS_WITH_WARNING
LATEST_COLLECTION_STATUS=COMPLETED
LATEST_OBSERVE_STATUS=COMPLETED
ACTIVE_EXECUTION_VERSION=1.2.1
PORTFOLIO_STATE_ENGINE=IMPLEMENTED
PORTFOLIO_STATE_DECISIONS=ALLOW|CAUTION|BLOCK
ENTRY_QUALITY_DEFAULT=0.10
OPEN_POSITION_GUARD=ACTIVE
TRADE_OUTCOME_FIELDS=entry_quality_score|entry_quality_score_known|position_source
ALLOCATION_LOSS_REFLECTION=ACTIVE
ALLOCATION_FACTORS=negative_pnl_penalty|loss_penalty|negative_avg_penalty
BACKUP_ROOT=C:\nt_v1\var\backups
ACTIVE_BACKUP_FOLDER=C:\nt_v1\var\backups\v1.2.1
BACKUP_NAME_RULE={relative_path}.{version}.{stage}.{timestamp}.bak
BACKUP_STAGE_REQUIRED=YES
```

