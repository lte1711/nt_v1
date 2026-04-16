from __future__ import annotations

import sys
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from next_trade.api.app import app  # noqa: E402


def main() -> int:
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8100,
        http="h11",
        loop="asyncio",
        lifespan="off",
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
