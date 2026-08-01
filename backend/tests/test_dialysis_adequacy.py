"""Unit tests for dialysis adequacy math (URR + Kt/V). No DB/server needed."""
import pytest

from app.services.dialysis_adequacy import compute_adequacy


def test_reference_case():
    # pre 30, post 9 → R=0.3 → URR 70%, Daugirdas Kt/V ≈ 1.42
    urr, kt_v = compute_adequacy(pre_urea=30, post_urea=9, hours=4, uf_litres=2.5, post_weight=70)
    assert urr == 70.0
    assert 1.3 < kt_v < 1.6
    assert abs(kt_v - 1.42) < 0.05


def test_higher_clearance_gives_higher_ktv():
    _, low = compute_adequacy(30, 12, 4, 2.0, 70)   # R=0.4
    _, high = compute_adequacy(30, 6, 4, 2.0, 70)    # R=0.2
    assert high > low


def test_zero_pre_urea_raises():
    with pytest.raises(ValueError):
        compute_adequacy(pre_urea=0, post_urea=9, hours=4, uf_litres=2.5, post_weight=70)


def test_zero_post_weight_raises():
    with pytest.raises(ValueError):
        compute_adequacy(pre_urea=30, post_urea=9, hours=4, uf_litres=2.5, post_weight=0)
