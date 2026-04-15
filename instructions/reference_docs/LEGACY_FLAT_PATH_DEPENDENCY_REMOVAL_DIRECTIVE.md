# NEXT-TRADE Legacy Flat Path Dependency Removal Directive

## Purpose

This directive defines the required path migration before any reversible hold rename can be executed on legacy role folders.

## Fact Base

The following files currently reference the flat legacy Honey report path directly:

```text
BOOT\boot_watchdog.ps1
BOOT\check_reboot_1m.ps1
BOOT\collect_runtime_8h.ps1
BOOT\first_order_milestone_reporter.ps1
BOOT\observe_multi5_realtime.ps1
BOOT\phase10_live_alpha_selection_pipeline.py
BOOT\phase11_live_alpha_portfolio_engine.py
BOOT\phase13b_goal_notifier.ps1
BOOT\phase5_autoguard.ps1
BOOT\phase5_portfolio_milestone_reporter.ps1
BOOT\phase8_multi_strategy_intelligence.py
BOOT\phase9_alpha_factory_pipeline.py
BOOT\runtime_guard.ps1
BOOT\start_8h_collection.ps1
BOOT\start_realtime_observe.ps1
BOOT\worker_watchdog.ps1
NEXT-TRADE\tools\dashboard\multi5_dashboard_config.py
NEXT-TRADE\tools\dashboard\multi5_dashboard_server.py
```

## Problem

```text
As long as these direct flat-path references remain,
renaming reports\honey_execution_reports or reports\candy_validation_reports
can break runtime logging, dashboard reads, and BOOT automation.
```

## Required Migration Direction

### RULE-P1 No Direct Flat Path

Replace hardcoded flat paths such as:

```text
C:\nt_v1\ver2_report\reports\honey_execution_reports\...
```

with one of:

```text
1. Daily folder resolver
2. Config-driven report root resolver
3. Legacy fallback-aware path helper
```

### RULE-P2 Daily Folder First

Preferred read/write order:

```text
1. reports\YYYY-MM-DD\<role_folder>\
2. legacy flat folder fallback only when explicitly needed
```

### RULE-P3 Runtime Writer Priority

The first migration targets are runtime writers:

```text
phase5_autoguard.ps1
runtime_guard.ps1
worker_watchdog.ps1
start_realtime_observe.ps1
start_8h_collection.ps1
observe_multi5_realtime.ps1
```

### RULE-P4 Dashboard Reader Migration

Dashboard readers must be migrated after runtime writers:

```text
multi5_dashboard_config.py
multi5_dashboard_server.py
```

### RULE-P5 Hold Rename Blocker

Reversible hold rename remains blocked until:

```text
1. flat-path runtime writers migrated
2. dashboard readers migrated
3. dependency re-scan returns no active operational flat-path references
```

## Output Requirement

Dependency removal work must produce:

```text
LEGACY_PATH_DEPENDENCY_REMOVAL_REPORT.txt
LEGACY_PATH_DEPENDENCY_SCAN.txt
```

