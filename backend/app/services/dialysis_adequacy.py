"""Dialysis adequacy computation: URR and Kt/V.

URR (Urea Reduction Ratio) = (1 − post/pre) × 100.
Kt/V via the Daugirdas second-generation single-pool formula:

    Kt/V = −ln(R − 0.008·t) + (4 − 3.5·R)·(UF/W)

where R = post_urea/pre_urea, t = session hours, UF = litres removed,
W = post-dialysis weight (kg).
"""
import math
from typing import Tuple


def compute_adequacy(
    pre_urea: float,
    post_urea: float,
    hours: float,
    uf_litres: float,
    post_weight: float,
) -> Tuple[float, float]:
    """Return (urr_pct, kt_v). Raises ValueError on non-physiological inputs."""
    if not pre_urea or pre_urea <= 0:
        raise ValueError("pre_urea must be > 0")
    if post_urea is None or post_urea < 0:
        raise ValueError("post_urea must be >= 0")
    if not post_weight or post_weight <= 0:
        raise ValueError("post_weight must be > 0")

    R = post_urea / pre_urea
    urr = (1.0 - R) * 100.0

    inner = R - 0.008 * hours
    if inner <= 0:
        # Guard the logarithm against unrealistic pre/post ratios.
        raise ValueError("R - 0.008*t must be > 0 for Kt/V")
    kt_v = -math.log(inner) + (4.0 - 3.5 * R) * (uf_litres / post_weight)

    return round(urr, 1), round(kt_v, 2)
