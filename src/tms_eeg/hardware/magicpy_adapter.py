"""Local, opt-in IPI compatibility adapter for MagicPy 0.1.6.

The 1 ms lower bound reproduces the reference project's patch; the local
adapter extends encoding to 200 ms. Software
acceptance does not establish the connected device's physical capabilities.
"""
import math
from numbers import Real

import magicpy as mp


def ipi_ticks(ipi):
    """Validate an explicit IPI and return its integer tenths of milliseconds."""
    if isinstance(ipi, bool) or not isinstance(ipi, Real):
        raise ValueError("IPI must be a finite number in milliseconds.")
    if not math.isfinite(ipi) or not 1 <= ipi <= 200:
        raise ValueError("IPI must be between 1 and 200 ms inclusive.")
    ticks = round(ipi * 10)
    if not math.isclose(ipi * 10, ticks, rel_tol=0, abs_tol=1e-9):
        raise ValueError("IPI must be representable in 0.1 ms increments.")
    return ticks


class PairedPulseMagVenture(mp.MagVenture):
    """Encode 1–200 ms IPIs; device resolution is checked by the controller."""

    def parse_ipi(self, ipi):
        ticks = ipi_ticks(ipi)
        # Encode exact integer ticks, avoiding hexlm's float truncation.
        encoded = f"{ticks:04x}"
        return encoded[2:4], encoded[0:2]