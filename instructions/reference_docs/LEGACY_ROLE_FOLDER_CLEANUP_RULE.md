# NEXT-TRADE Legacy Role Folder Cleanup Rule

## Purpose

This document defines the fact-aligned cleanup rule for legacy role folders after copy-first migration.

## Fact Base

```text
ROOT_REPORT_PATH
C:\nt_v1\ver2_report\reports

LEGACY_ROLE_FOLDERS_PRESENT
honey_execution_reports
candy_validation_reports

FIRST_COPY_FIRST_MIGRATION_DONE
YES

MANIFEST_PRESENT
LEGACY_ROLE_REPORT_MIGRATION_MANIFEST_2026-03-15.csv
LEGACY_ROLE_REPORT_MIGRATION_MANIFEST_2026-03-15.json
```

## Cleanup Principle

```text
1. Do not delete legacy files immediately after copy.
2. Validate source and target parity first.
3. Use reversible cleanup markers before any destructive action.
4. Preserve rollback simplicity.
```

## Cleanup States

### STATE-C1 Active Legacy

```text
Source legacy files still exist in the original flat role folders.
No cleanup action yet.
```

### STATE-C2 Verified Legacy

```text
Manifest validation passed for:
- source exists
- target exists
- byte size matches
```

### STATE-C3 Quarantine-Ready

```text
Legacy source files may be renamed or moved into a reversible quarantine marker state,
but not permanently deleted.
```

### STATE-C4 Final Deletion Hold

```text
Permanent deletion remains blocked until a separate approval rule exists.
```

## Cleanup Rule

### RULE-C1 Validation First

Cleanup cannot start unless:

```text
1. migration manifest exists
2. migration validation report exists
3. missing_targets = 0
4. size_mismatches = 0
```

### RULE-C2 Reversible First

Allowed first cleanup action:

```text
rename legacy folder to *_legacy_verified_hold
```

Examples:

```text
honey_execution_reports -> honey_execution_reports_legacy_verified_hold
candy_validation_reports -> candy_validation_reports_legacy_verified_hold
```

### RULE-C3 No Immediate Deletion

The following actions remain blocked:

```text
Remove-Item on legacy role folders
permanent deletion of source reports
bulk cleanup of phase folders
```

### RULE-C4 Phase Folder Exclusion

```text
phase* folders
first_order_observation
experiment-specific evidence trees
```

stay out of cleanup scope.

### RULE-C5 Cleanup Approval Gate

Final deletion requires:

```text
1. validated manifest
2. explicit cleanup approval
3. rollback note
4. quarantine window completed
```

### RULE-C6 Active Runtime File Exception

The following file types stay out of cleanup until they are no longer changing:

```text
live *.jsonl append logs
live *_status.txt files
live *_log.txt files
```

Reason:

```text
copy-first validation can show size mismatch if runtime keeps appending after the copy.
This is not evidence of a bad copy by itself.
```

## Recommended Immediate Action

```text
1. Run manifest validation
2. If validation passes, keep legacy folders unchanged or apply reversible hold rename only
3. Do not delete anything yet
```

