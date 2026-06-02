"""Bootstrap for the (DB-free) email unit tests.

These tests never touch a database — they exercise the email service,
templates, and dispatch helpers in isolation. We still load backend/.env (when
present) so ``app.config.settings`` imports cleanly with valid SECRET_KEY /
ENCRYPTION_KEY / DATABASE_URL; in CI those come from the workflow env instead.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(_BACKEND_DIR / ".env")
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
