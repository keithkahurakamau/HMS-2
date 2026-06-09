"""Pay Hero webhook amount-integrity guards (security audit C-1 / H-3 / M-3).

Pure-function coverage for the two helpers the callback workers rely on:
  * parse_callback_amount  — fail-loud on non-numeric/negative (M-3)
  * _tenant_id_from_plat_ref — re-derive tenant from the PLAT- reference (H-3)

The full settlement paths (C-1 overpay refusal, M-4 status regression) are
exercised end-to-end by the live-DB payment tests; here we lock the parsing
and reference-binding logic that the refusal decisions are built on.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.payhero_service import parse_callback_amount
from app.services.platform_payhero_service import _tenant_id_from_plat_ref


# ─── parse_callback_amount (M-3) ───────────────────────────────────────────

def test_blank_or_missing_amount_is_zero_not_error():
    assert parse_callback_amount(None) == Decimal(0)
    assert parse_callback_amount("") == Decimal(0)
    assert parse_callback_amount("   ") == Decimal(0)


def test_numeric_amounts_parse():
    assert parse_callback_amount("100") == Decimal("100")
    assert parse_callback_amount(100) == Decimal("100")
    assert parse_callback_amount("99.50") == Decimal("99.50")


@pytest.mark.parametrize("bad", ["abc", "1,000", "10x", "NaN", "Infinity"])
def test_non_numeric_amount_raises(bad):
    # A present-but-garbage amount must NOT floor to zero and silently settle.
    with pytest.raises(ValueError):
        parse_callback_amount(bad)


def test_negative_amount_raises():
    with pytest.raises(ValueError):
        parse_callback_amount("-50")


# ─── _tenant_id_from_plat_ref (H-3) ────────────────────────────────────────

def test_plat_ref_tenant_parsed():
    assert _tenant_id_from_plat_ref("PLAT-42-ab12cd34") == 42


def test_plat_ref_non_plat_shape_is_none():
    assert _tenant_id_from_plat_ref("INV-7-abcd") is None
    assert _tenant_id_from_plat_ref("") is None
    assert _tenant_id_from_plat_ref("PLAT-notanint-xyz") is None
