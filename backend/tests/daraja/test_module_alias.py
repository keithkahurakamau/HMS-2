"""core/modules.py's payhero -> mpesa legacy alias.

resolve_enabled_modules is a pure function (no DB), so these are direct
unit tests rather than route-level ones. mpesa defaults to enabled
(ModuleDef's default_enabled=True), which is exactly what makes the
explicit-False direction easy to get wrong: forgetting it means a tenant
that turned M-Pesa off via the old payhero key sees mpesa silently
re-appear anyway, on nothing more than the module's own default.

Pay Hero itself (the "payhero" ModuleDef) was removed in the Daraja
migration's Task 12, so a stored ``payhero`` flag is no longer a real
module and never appears in the enabled set on its own; these tests now
check only that it still forward-fills ``mpesa``, not that it enables
itself.
"""
from __future__ import annotations

import json

from app.core.modules import resolve_enabled_modules


def _flags(**kwargs) -> str:
    return json.dumps(kwargs)


def test_payhero_true_forward_fills_mpesa():
    enabled = resolve_enabled_modules(_flags(payhero=True))
    # "payhero" is no longer a real ModuleDef (removed in Task 12), so it
    # never appears in the enabled set itself; only the forward-fill to
    # "mpesa" is the behaviour under test.
    assert "payhero" not in enabled
    assert "mpesa" in enabled


def test_payhero_false_forward_fills_mpesa_false_too():
    """The bug this test guards against: mpesa is default-enabled, so a
    tenant with no explicit mpesa key and payhero=False must still end up
    with mpesa disabled, not silently re-enabled by its own default."""
    enabled = resolve_enabled_modules(_flags(payhero=False))
    assert "payhero" not in enabled
    assert "mpesa" not in enabled


def test_explicit_mpesa_flag_is_never_overridden_by_the_payhero_alias():
    # An explicit mpesa=True survives a payhero=False neighbour: the alias
    # only ever fills a MISSING mpesa key, never overwrites one already set.
    enabled = resolve_enabled_modules(_flags(payhero=False, mpesa=True))
    assert "mpesa" in enabled

    enabled = resolve_enabled_modules(_flags(payhero=True, mpesa=False))
    assert "mpesa" not in enabled


def test_no_flags_at_all_defaults_mpesa_enabled():
    assert "mpesa" in resolve_enabled_modules(None)
    assert "mpesa" in resolve_enabled_modules("{}")
