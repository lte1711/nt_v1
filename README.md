# NEXT-TRADE

NEXT-TRADE is a Windows-oriented trading runtime project that combines:

- a FastAPI ops/investor API on port `8100`
- a dashboard server on port `8788`
- a Multi5 engine runtime and supporting watchdog scripts

## Project root

This repository is expected to run from its current checkout path. The main startup scripts now resolve the project root relative to their own file location, so the project no longer depends on a previously fixed install path.

## Quick start

Use the virtual environment in `.venv` and start the full local stack:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_project.ps1
```

## Verification

Run the built-in checks with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_checks.ps1
```

This verification path uses:

- `py_compile` for core Python entry points
- `unittest discover` for the test suite in `tests/`

`pytest` is not required for the default verification path.

## Smoke test

After startup, run a short runtime smoke test with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke_test.ps1
```

This validates:

- API TCP + HTTP health on `8100`
- dashboard TCP + HTTP health on `8788`
- engine process presence
