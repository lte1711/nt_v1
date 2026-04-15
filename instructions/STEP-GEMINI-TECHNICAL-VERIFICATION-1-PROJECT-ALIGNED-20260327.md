# STEP-GEMINI-TECHNICAL-VERIFICATION-1 PROJECT-ALIGNED

## 1) 역할 고정

### [FACT]

```text
CURRENT_EXECUTION_OWNER=CODEX
CURRENT_TECHNICAL_VERIFIER=GEMINI
CURRENT_DATA_VALIDATOR=CANDY
FINAL_APPROVER=DENNIS
CONSTITUTION_PATH=C:\nt_v1\instructions\NEXT-TRADE-CONSTITUTION-FINAL.md
```

### [FACT]

```text
CURRENT_STAGE=POST_CODEX_READ_ONLY_EVIDENCE_COLLECTION
MODIFICATION=PROHIBITED
RESTART=PROHIBITED
PATCH=PROHIBITED
EVIDENCE_BASE=PROJECT_ROOT_INTERNAL_FILES_AND_LOGS_ONLY
```

## 2) 프로젝트 정합화 반영

### [FACT]

```text
PROJECT_ROOT=C:\nt_v1
BOOT_ROOT=C:\nt_v1\BOOT
OFFICIAL_ENGINE_ENTRY=C:\nt_v1\BOOT\start_engine.ps1
ACTUAL_BOOT_TO_WORKER_CHAIN=C:\nt_v1\BOOT\start_engine.ps1 -> C:\nt_v1\tools\multi5\run_multi5_engine.py -> C:\nt_v1\tools\ops\profitmax_v1_runner.py
RUNTIME_GUARD_CHAIN=C:\nt_v1\BOOT\start_runtime_guard.ps1 -> C:\nt_v1\BOOT\runtime_guard.ps1 -> C:\nt_v1\BOOT\start_engine.ps1
AUTOGUARD_CHAIN=C:\nt_v1\BOOT\phase5_autoguard.ps1 -> C:\nt_v1\BOOT\start_runtime_guard.ps1 -> C:\nt_v1\BOOT\start_engine.ps1
```

### [FACT]

```text
DO_NOT_USE_NONEXISTENT_PATH=src/engine/main_loop.py
PRIMARY_VERIFICATION_TARGET=C:\nt_v1\tools\ops\profitmax_v1_runner.py
PRIMARY_RUNTIME_LOG=C:\nt_v1\logs\runtime\profitmax_v1_events.jsonl
PRIMARY_KPI_FILE=C:\nt_v1\logs\runtime\portfolio_metrics_snapshot.json
```

## 3) Gemini 단일 작업 지시

### STEP-GEMINI-TECHNICAL-VERIFICATION-1-PROJECT-ALIGNED

#### 작업 1 - HARD_RESET 도달 조건 판정

```text
검증 대상:
1. C:\nt_v1\tools\ops\profitmax_v1_runner.py
2. C:\nt_v1\logs\runtime\profitmax_v1_events.jsonl

핵심 증거:
A. EMERGENCY_MONITOR_VALIDATE_DELEGATED
B. validate_position_state() 호출
C. STATE_VALIDATION_ERROR
D. HARD_RESET

판정 목표:
HARD_RESET이 어떤 예외/조건에서 직접 발생하는지 코드와 로그를 연결해 확정
```

완료 기준

```text
HARD_RESET_TRIGGER_CONDITION_CONFIRMED=YES/NO
HARD_RESET_PRECEDING_EVENT_CHAIN_CONFIRMED=YES/NO
```

#### 작업 2 - RECONCILE 우선 보장 여부 판정

```text
검증 대상:
1. C:\nt_v1\tools\ops\profitmax_v1_runner.py
2. C:\nt_v1\logs\runtime\profitmax_v1_events.jsonl

핵심 증거:
A. STATE_API_SOURCE_OF_TRUTH_APPLIED
B. STATE_COUNT_MISMATCH_TELEMETRY
C. _reconcile_local_position(...)
D. STATE_RECONCILE_APPLIED
E. HARD_RESET 부재 또는 후행 여부

판정 목표:
LOG_API_COUNT_MISMATCH 상황에서 HARD_RESET 대신 RECONCILE이 우선 적용되는지 구조와 실로그로 확정
```

완료 기준

```text
RECONCILE_PRIORITY_CONFIRMED=YES/NO
RECONCILE_BEFORE_RESET_FOR_COUNT_MISMATCH=YES/NO
```

#### 작업 3 - KPI 미집계 직접 원인 판정

```text
검증 대상:
1. C:\nt_v1\logs\runtime\portfolio_metrics_snapshot.json
2. C:\nt_v1\logs\runtime\profitmax_v1_events.jsonl
3. C:\nt_v1\tools\ops\profitmax_v1_runner.py
4. 헌법 KPI 요구: total_pnl|win_rate|max_drawdown|trade_count|sharpe_ratio|avg_holding_time

핵심 증거:
A. KPI 실파일 필드 목록
B. HEARTBEAT payload 내 session_realized_pnl|daily_realized_pnl|daily_trades
C. portfolio_metrics_snapshot.json 내 realized_pnl|win_rate|drawdown|total_trades
D. max_drawdown, trade_count, sharpe_ratio, avg_holding_time의 직접 필드 부재 여부

판정 목표:
KPI 미집계가 계산 부재인지, 파일 스키마 불일치인지, 출력 위치 분산인지 구분
```

완료 기준

```text
KPI_DIRECT_CAUSE_CLASSIFIED=YES/NO
KPI_SCHEMA_MISMATCH_CONFIRMED=YES/NO
KPI_OUTPUT_SPLIT_CONFIRMED=YES/NO
```

## 4) 금지 사항

```text
1. 엔진 재시작 금지
2. 프로세스 종료 금지
3. 설정 변경 금지
4. 소스 코드 수정 금지
5. KPI 로직 수정 금지
6. BOOT 스크립트 수정 금지
```

## 5) 보고서 형식

```text
# STEP-GEMINI-TECHNICAL-VERIFICATION-1 PROJECT-ALIGNED RESULT

[FACT]
BOOT_CHAIN = ...
WORKER_CHAIN = ...
HARD_RESET_TRIGGER_CHAIN = ...
RECONCILE_TRIGGER_CHAIN = ...
KPI_RUNTIME_FILE = ...
KPI_FIELD_MISMATCH = ...

[INFERENCE]
- FACT에서 직접 도출되는 최소 추론만 기재

[ASSUMPTION]
- 없으면 NONE

[UNKNOWN]
- 현재 증거만으로 확정 불가한 항목만 기재

[FINAL_JUDGMENT]
HARD_RESET_TRIGGER_CONDITION_CONFIRMED = YES/NO
RECONCILE_PRIORITY_CONFIRMED = YES/NO
KPI_DIRECT_CAUSE_CLASSIFIED = YES/NO
NEXT_ACTION = CANDY_RECHECK / CODEX_ADDITIONAL_READ_ONLY / DENNIS_REVIEW
```

