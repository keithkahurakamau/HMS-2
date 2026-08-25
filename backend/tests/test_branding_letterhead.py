"""Letterhead print-template config — validation and carry-forward rules.

Pure unit tests: no live server, no database. The letterhead lives inside the
existing ``tenants.print_templates`` JSON column (deliberately — reusing it
keeps the migration gate a no-op), so the interesting behaviour is the
serialisation and merge logic around that column rather than any schema change.
"""
from __future__ import annotations

import json
import sys
import os

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.routes.branding import (  # noqa: E402
    LetterheadConfig,
    PrintTemplateConfig,
    _stored_templates,
    _validate_letterhead,
    MAX_LETTERHEAD_BYTES,
)

JPEG = "data:image/jpeg;base64,AAAA"


class FakeTenant:
    """Just the one column the helpers touch."""
    def __init__(self, print_templates=None):
        self.print_templates = print_templates


# ── _stored_templates ───────────────────────────────────────────────────────
def test_stored_templates_empty_when_unset():
    assert _stored_templates(FakeTenant(None)) == {}


def test_stored_templates_parses_json():
    t = FakeTenant(json.dumps({"header_text": "Clinic"}))
    assert _stored_templates(t) == {"header_text": "Clinic"}


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '"a string"', "null"])
def test_stored_templates_tolerates_bad_rows(raw):
    """Legacy or hand-edited rows must not 500 the branding endpoint."""
    assert _stored_templates(FakeTenant(raw)) == {}


# ── _validate_letterhead ────────────────────────────────────────────────────
def test_accepts_jpeg_png_and_webp():
    for url in ("data:image/jpeg;base64,AA", "data:image/png;base64,AA",
                "data:image/webp;base64,AA"):
        _validate_letterhead(LetterheadConfig(enabled=True, image=url))


def test_rejects_svg_which_can_carry_script():
    with pytest.raises(HTTPException) as exc:
        _validate_letterhead(LetterheadConfig(enabled=True, image="data:image/svg+xml;base64,AA"))
    assert exc.value.status_code == 400
    assert "svg" in exc.value.detail.lower()


def test_rejects_non_image_url():
    with pytest.raises(HTTPException) as exc:
        _validate_letterhead(LetterheadConfig(enabled=True, image="https://example.com/x.jpg"))
    assert exc.value.status_code == 400


def test_rejects_oversized_artwork():
    huge = "data:image/jpeg;base64," + ("A" * MAX_LETTERHEAD_BYTES)
    with pytest.raises(HTTPException) as exc:
        _validate_letterhead(LetterheadConfig(enabled=True, image=huge))
    assert exc.value.status_code == 413


def test_enabling_without_artwork_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate_letterhead(LetterheadConfig(enabled=True, image=None))
    assert exc.value.status_code == 400


def test_disabled_without_artwork_is_fine():
    """The default state for every tenant that never uploads one."""
    _validate_letterhead(LetterheadConfig(enabled=False, image=None))


def test_rejects_margins_that_leave_no_printable_height():
    with pytest.raises(HTTPException) as exc:
        _validate_letterhead(LetterheadConfig(
            enabled=True, image=JPEG, margin_top_mm=150, margin_bottom_mm=150))
    assert exc.value.status_code == 400
    assert "printable area" in exc.value.detail


def test_side_margin_is_bounded_by_the_field_itself():
    """Width can't be swallowed the way height can — the 60 mm field cap means
    2 x side is always < 210 mm — so the bound is enforced at the schema."""
    with pytest.raises(ValidationError):
        LetterheadConfig(enabled=True, image=JPEG, margin_side_mm=105)
    # The largest accepted value still leaves printable width.
    _validate_letterhead(LetterheadConfig(enabled=True, image=JPEG, margin_side_mm=60))


# ── schema shape ────────────────────────────────────────────────────────────
def test_margins_default_to_the_measured_a4_safe_area():
    cfg = LetterheadConfig()
    assert (cfg.margin_top_mm, cfg.margin_bottom_mm, cfg.margin_side_mm) == (42, 48, 18)


def test_out_of_range_margin_is_a_validation_error():
    with pytest.raises(ValidationError):
        LetterheadConfig(margin_top_mm=500)


def test_print_templates_without_letterhead_still_valid():
    """Tenants that only set header/footer text must keep working unchanged."""
    cfg = PrintTemplateConfig(header_text="Outpatient Dept")
    assert cfg.letterhead is None
    assert "letterhead" not in cfg.model_dump(exclude_none=True)


def test_letterhead_round_trips_through_the_json_column():
    cfg = PrintTemplateConfig(
        header_text="Consultant Physician",
        letterhead=LetterheadConfig(enabled=True, image=JPEG, margin_top_mm=40),
    )
    stored = json.dumps(cfg.model_dump(exclude_none=True))
    back = _stored_templates(FakeTenant(stored))
    assert back["letterhead"]["image"] == JPEG
    assert back["letterhead"]["margin_top_mm"] == 40
    assert back["header_text"] == "Consultant Physician"
