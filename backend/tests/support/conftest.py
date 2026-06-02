"""Bootstrap for the (DB-free) inbound-support unit tests.

These exercise the pure parsing/threading/signature helpers in isolation.
Loads backend/.env (when present) so app.config.settings imports cleanly; in
CI the values come from the workflow env instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_DIR / ".env")
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
