"""Ensure src/ is on sys.path for tests without requiring PYTHONPATH env var."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).parent / "src"
if SRC.is_dir():
    sp = str(SRC)
    if sp not in sys.path:
        sys.path.insert(0, sp)
