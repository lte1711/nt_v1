# NEXT-TRADE Report Archive Migration Rule

## Purpose

This document defines the fact-aligned migration rule for moving from legacy flat report storage to the Daily Evidence Folder System.

## Fact Base

```text
ROOT_REPORT_PATH
C:\nt_v1\ver2_report\reports

CURRENT_DAILY_FOLDER_PRESENT
2026-03-15

CURRENT_LEGACY_FLAT_FOLDERS_PRESENT
honey_execution_reports
candy_validation_reports
phase5_7_runtime
phase6_runtime
phase7_strategy
phase8_multi_strategy
phase9_alpha_factory
phase10_live_alpha_selection
phase11_live_alpha_portfolio
phase12_strategy_forensics
phase12_strategy_patch
phase12_strategy_surgery
phase13_same_window_pf
first_order_observation
```

## Migration Principle

```text
1. Do not bulk-move historical folders without classification.
2. Preserve historical paths until a manifest exists.
3. Use copy-first, verify-second, remove-last.
4. Role-based reports and phase-based evidence must not be mixed blindly.
```

## Folder Classes

### Class A: Daily Role-Based Archive

```text
reports\YYYY-MM-DD\
 ├─ honey_execution_reports
 ├─ candy_validation_reports
 ├─ gemini_technical_reports
 ├─ sugar_audit_reports
 └─ baekseol_design_reports
```

### Class B: Legacy Role Folders

```text
reports\honey_execution_reports
reports\candy_validation_reports
```

These are migration candidates because they match the new role-based naming pattern but are stored outside dated folders.

### Class C: Phase and Experiment Evidence Folders

```text
reports\phase*
reports\first_order_observation
```

These are not immediate migration targets for the Daily Folder System because they represent long-lived phase evidence, not single-day role output.

## Migration Rule

### RULE-M1 Manifest First

Before any file move, create a manifest that records:

```text
source_path
target_path
file_count
date_basis
role_owner
move_type = copy-first
```

### RULE-M2 Role Folder Migration Only

Immediate migration scope is limited to:

```text
reports\honey_execution_reports
reports\candy_validation_reports
reports\gemini_technical_reports
reports\sugar_audit_reports
reports\baekseol_design_reports
```

if those folders exist outside a dated folder.

### RULE-M3 Date Resolution

Historical files may be moved into dated folders only when one of the following is present:

```text
1. File name includes YYYYMMDD or YYYY-MM-DD
2. File content or report header contains a reliable report date
3. LastWriteTime is explicitly approved as fallback evidence
```

If no reliable date basis exists, keep the file in legacy storage until classified.

### RULE-M4 Copy First

Migration order:

```text
1. copy file
2. verify byte size and destination presence
3. verify manifest entry
4. only then consider source cleanup
```

### RULE-M5 Phase Folder Freeze

The following classes remain frozen until a separate archive policy is approved:

```text
phase folders
first_order_observation
experiment-specific evidence trees
```

## Recommended Next Steps

```text
1. Use ensure_daily_report_folders.ps1 for all new reports
2. Build a migration manifest for legacy role folders only
3. Do not move phase folders under the daily archive yet
```

