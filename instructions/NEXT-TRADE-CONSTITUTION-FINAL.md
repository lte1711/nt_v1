# NEXT-TRADE CONSTITUTION v1.2.1

## Status

```text
CONSTITUTION_STATUS=ACTIVE
CONSTITUTION_VERSION=1.2.1
LAST_UPDATED=2026-03-29
CONSTITUTION_FILE=C:\nt_v1\instructions\NEXT-TRADE-CONSTITUTION-FINAL.md
APPROVAL_STATUS=TEAM_CONSENSUS_REQUIRED
```

## Root Paths

```text
PROJECT_ROOT=C:\nt_v1
BOOT_ROOT=C:\nt_v1\BOOT
OFFICIAL_ENGINE_ENTRY=C:\nt_v1\BOOT\start_engine.ps1
VENV_ROOT=C:\nt_v1\.venv
TOOLS_ROOT=C:\nt_v1\tools
STRATEGY_ROOT=C:\nt_v1\strategies
SRC_ROOT=C:\nt_v1\src
DATA_ROOT=C:\nt_v1\data
LOG_ROOT=C:\nt_v1\logs
REPORT_ROOT=C:\nt_v1\reports
INSTRUCTION_ROOT=C:\nt_v1\instructions
VAR_ROOT=C:\nt_v1\var
OPS_UI_ROOT=C:\nt_v1\evergreen-ops-ui
LEGACY_ROOT=C:\projects
```

## Execution Policy

```text
VERIFY_FIRST_POLICY=ACTIVE
BOOT_EXECUTION_PREFERENCE=ACTIVE
RULE_STEP_BY_STEP=ACTIVE
RULE_FACT_ONLY=ACTIVE
RULE_ASSUMPTION_LABELING=ACTIVE
RULE_EVIDENCE_REQUIREMENT=ACTIVE
WORKFLOW=BAEKSEOL->CODEX->CANDY->GEMINI->DENNIS
SYSTEM_KPI_STANDARD=SNAPSHOT
BASE_CONSTITUTION_MODE=FACT_ONLY
```

## Constitution Version 1.2.1 Fixed Facts

```text
LATEST_AUDITED_SESSION_DATE=2026-03-29
LATEST_AUDITED_SESSION_GRADE=PASS_WITH_WARNING
LATEST_AUDITED_COLLECTION_STATUS=COMPLETED
LATEST_AUDITED_OBSERVE_STATUS=COMPLETED
ACTIVE_EXECUTION_VERSION=1.2.1
```

## Core Operating Rules

- Read the constitution before any execution.
- Execute only under `PROJECT_ROOT`.
- Do not execute runtime from `LEGACY_ROOT`.
- Preserve `start_engine.ps1 -> runtime_guard -> phase5_autoguard`.
- Confirm all claims with logs, files, ports, or API evidence.
- Execute one member, one step, then report before the next directive.
- Use `FACT / INFERENCE / ASSUMPTION / UNKNOWN` labels in reports.
- Do not update the constitution without direct file or log verification.
- Do not write inferred causes as `FACT`.

## Role Alignment

```text
DENNIS=final_approval
BAEKSEOL=design_and_instruction
CODEX=execution_manager_and_execution
CANDY=data_analysis_and_validation
GEMINI=technical_verification
SUGAR=external_audit
```

## Operating Mode

```text
MODE=STRATEGY_DEVELOPMENT_ACTIVE
GOALS=build_auto_trading_strategies|validate_on_binance_testnet|compare_and_optimize_strategy_performance
```

## KPI Standard

```text
KPI_SOURCE=portfolio_metrics_snapshot.json
KPI_RECOMPUTED_FROM=profitmax_v1_events.jsonl
KPI_FIELDS=total_trades|realized_pnl|win_rate|drawdown
RUNTIME_STATS_USAGE=NON_KPI_REFERENCE_ONLY
```

## Runtime And Audit Facts Fixed In v1.2

```text
PORTFOLIO_STATE_ENGINE_FILE=C:\nt_v1\tools\portfolio_state_engine.py
PORTFOLIO_STATE_ENGINE_MODE=IMPLEMENTED
PORTFOLIO_STATE_DECISIONS=ALLOW|CAUTION|BLOCK
RUNNER_ENTRY_QUALITY_DEFAULT=0.10
RUNNER_OPEN_POSITION_GUARD=ACTIVE
RUNNER_TRADE_OUTCOME_FIELDS=entry_quality_score|entry_quality_score_known|position_source
RUNNER_STRATEGY_STATS_SOURCE_PRIORITY=strategy_performance.json->local_runner_summary
ALLOCATION_LOSS_REFLECTION=ACTIVE
ALLOCATION_LOSS_FACTORS=negative_pnl_penalty|loss_penalty|negative_avg_penalty
```

## Backup Policy Fixed In v1.2.1

```text
BACKUP_ROOT=C:\nt_v1\var\backups
ACTIVE_BACKUP_SERIES=v1.2.1
ACTIVE_BACKUP_FOLDER=C:\nt_v1\var\backups\v1.2.1
BACKUP_NAMING_RULE={relative_path}.{version}.{stage}.{timestamp}.bak
BACKUP_STAGE_REQUIRED=YES
BACKUP_STAGE_ALLOWED=pre_edit|post_edit|pre_run|post_run|pre_release|post_audit
```

## Prohibitions

- Non-CODEX execution.
- CANDY runtime intervention.
- Judgment without evidence.
- Cross-strategy state sharing.
- Mixing runtime stats with KPI judgment.
- Constitution updates without direct verification.
- Reporting inferred causes as FACT.

## Evidence Standards

```text
EVIDENCE=logs|files|api_responses|direct_measurements
```

## Evidence Classification

```text
FACT=directly verified from code, logs, files, api responses, or measurements
INFERENCE=minimal interpretation directly supported by verified facts
ASSUMPTION=explicitly labeled statement not directly verified
UNKNOWN=not confirmable with currently available evidence
```

## Fact-Only Execution Rule

- All execution, reporting, and constitution updates must be based on directly verified evidence.
- If a claim is not directly verified, it must not be written as `FACT`.
- If code behavior was changed, the change is not constitutionally fixed until the target file is re-read and directly verified.
- Session audit closure may be recorded as fact only after file-level or log-level reconciliation is complete.
- Every manual file edit requiring backup must store the backup under `ACTIVE_BACKUP_FOLDER`.
- Every backup filename must include both the active constitution version and the execution stage.

## Document Storage Rule

```text
ROOT_REPORT_PATH=C:\nt_v1\reports
DATE_FORMAT=YYYY-MM-DD
```

```text
YYYY-MM-DD\
  |- codex_execution_reports
  |- candy_validation_reports
  |- gemini_technical_reports
  |- sugar_audit_reports
  \- baekseol_design_reports
```

- Each team member stores reports only in the matching role folder.
- Daily folder creation responsibility order: `CODEX -> Candy -> BAEKSEOL`.
- Purpose: date-based audit, execution trace, team flow trace, and evidence-chain reproduction.

