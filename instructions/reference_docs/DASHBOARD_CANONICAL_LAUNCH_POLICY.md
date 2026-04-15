# Dashboard Canonical Launch Policy

## Purpose
Define the fact-aligned runtime policy for dashboard launch evaluation after duplicate-process hygiene.

## Current Facts
- The dashboard currently stabilizes as two python processes for the same script.
- Only one process owns the 8787 listener.
- The dashboard API returns HTTP 200.
- The launch path starts from the project venv python executable.
- The listener process currently appears as the system Python executable child.

## Policy
### Rule P1: Canonical Health Signal
Dashboard health must be judged first by:
1. one active listener on port 8787
2. one reachable dashboard API returning HTTP 200
3. at least one process matching `multi5_dashboard_server.py`

### Rule P2: Do Not Treat 2-Process Parent-Child State as Duplicate by Default
If the dashboard shows:
- one 8787 listener
- API 200
- a parent-child process chain for the same script
then this state must not be auto-cleaned as a duplicate conflict.

### Rule P3: Duplicate Conflict Definition
A duplicate conflict exists only when one of the following is true:
1. multiple listeners exist on 8787
2. API is failing and multiple dashboard processes exist
3. multiple independent root dashboard launch chains exist

### Rule P4: Preferred Launch Path
The preferred launch command remains the project virtual environment python:
`C:\nt_v1\NEXT-TRADE\.venv\Scripts\python.exe C:\nt_v1\NEXT-TRADE\tools\dashboard\multi5_dashboard_server.py`

### Rule P5: Monitoring Scripts
Watchdog/autoguard logic must check listener and API health before process-count duplicate cleanup.

## Operational Meaning
- Single listener is the primary runtime truth.
- Process-count-only duplicate cleanup is unsafe for the current observed dashboard launch pattern.
- Future cleanup should target listener conflicts, not merely parent-child process count.

