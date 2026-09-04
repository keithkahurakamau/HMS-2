"""Loading docs/seed/pharmacy-catalogue.csv: missing file, empty file,
dedup, and whitespace/casing normalisation.

No DB, no live server: these exercise app.services.pharmacy_starter_catalogue
directly, monkeypatching the module's in-process cache and CSV path so each
test controls exactly what's "on disk" without touching the real repo file.
"""
from __future__ import annotations

import pytest

from app.services import pharmacy_starter_catalogue as svc


@pytest.fixture(autouse=True)
def _reset_cache():
    """The loader caches in process; every test needs a clean slate."""
    svc._cache = None
    yield
    svc._cache = None


def _point_at(monkeypatch, tmp_path, content: str | None):
    """Point the module's CSV path at a file under tmp_path. Passing None
    skips writing the file entirely, so the path just doesn't exist."""
    path = tmp_path / "pharmacy-catalogue.csv"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(svc, "_CSV_PATH", str(path))
    return path


class TestMissingOrEmpty:
    def test_missing_file_returns_empty_list_not_an_error(self, monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path, None)  # never written -> doesn't exist
        assert svc.load_catalogue() == []
        assert svc.catalogue_available() is False

    def test_header_only_file_is_empty(self, monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path, "name\n")
        assert svc.load_catalogue() == []
        assert svc.catalogue_available() is False

    def test_missing_name_column_is_empty(self, monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path, "sku,description\nA1,Something\n")
        assert svc.load_catalogue() == []
        assert svc.catalogue_available() is False

    def test_blank_rows_are_skipped(self, monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path, "name\n\n   \nParacetamol 500mg\n")
        assert svc.load_catalogue() == ["Paracetamol 500mg"]
        assert svc.catalogue_available() is True


class TestDeduplication:
    def test_duplicate_names_collapse_case_and_whitespace_insensitively(self, monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path, (
            "name\n"
            "Paracetamol 500mg\n"
            "paracetamol 500mg\n"
            "  Paracetamol   500mg  \n"
            "PARACETAMOL 500MG\n"
        ))
        products = svc.load_catalogue()
        assert products == ["Paracetamol 500mg"]

    def test_first_occurrence_display_form_wins(self, monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path, "name\nAmoxicillin 250mg\namoxicillin 250mg\n")
        products = svc.load_catalogue()
        assert products == ["Amoxicillin 250mg"]

    def test_distinct_products_are_both_kept_in_order(self, monkeypatch, tmp_path):
        _point_at(monkeypatch, tmp_path, "name\nZinc Sulphate\nAmoxicillin 250mg\n")
        assert svc.load_catalogue() == ["Zinc Sulphate", "Amoxicillin 250mg"]


class TestCaching:
    def test_second_call_does_not_reread_disk(self, monkeypatch, tmp_path):
        path = _point_at(monkeypatch, tmp_path, "name\nParacetamol 500mg\n")
        first = svc.load_catalogue()
        path.write_text("name\nSomething Else\n", encoding="utf-8")
        second = svc.load_catalogue()
        assert first == second == ["Paracetamol 500mg"]

    def test_force_reload_picks_up_changes(self, monkeypatch, tmp_path):
        path = _point_at(monkeypatch, tmp_path, "name\nParacetamol 500mg\n")
        svc.load_catalogue()
        path.write_text("name\nSomething Else\n", encoding="utf-8")
        assert svc.load_catalogue(force_reload=True) == ["Something Else"]


class TestNormalizeName:
    @pytest.mark.parametrize("raw,expected", [
        ("Paracetamol 500mg", "paracetamol 500mg"),
        ("  Paracetamol   500mg  ", "paracetamol 500mg"),
        ("PARACETAMOL 500MG", "paracetamol 500mg"),
    ])
    def test_normalize_name(self, raw, expected):
        assert svc.normalize_name(raw) == expected
