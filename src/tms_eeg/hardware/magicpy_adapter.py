"""Local serial diagnostics and IPI compatibility for MagicPy 0.1.6.

The 1 ms lower bound reproduces the reference project's patch; the local
adapter extends encoding to 200 ms. Software
acceptance does not establish the connected device's physical capabilities.
"""
import math
import time
from numbers import Real

import magicpy as mp
from tms_eeg import config
from tms_eeg.logger import log


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


class MagVenture(mp.MagVenture):
    """Expose complete readback and report the serial reads MagicPy performs."""

    def process_command(self, command_length, command_bytes, resp_len_exp=8, get_response=False):
        process = super().process_command
        if not get_response or not config.ENABLE_LOGGING:
            return process(command_length, command_bytes, resp_len_exp, get_response)

        # Instrument the inherited transaction without changing its byte handling,
        # timeouts or decoding. The acquisition loop owns the serial port.
        port = self.port
        read = port.read
        received = 0

        def read_and_count(*args, **kwargs):
            nonlocal received
            data = read(*args, **kwargs)
            received += len(data)
            return data

        parts = [command_bytes] if isinstance(command_bytes, str) else command_bytes
        command = " ".join(parts[:2])
        started_at = time.monotonic()
        port.read = read_and_count
        result = "exception"
        try:
            response, error = process(command_length, command_bytes, resp_len_exp, get_response)
            result = f"{type(response).__name__}, error={error!r}"
            if isinstance(response, str):
                result = f"{response!r}, error={error!r}"
            return response, error
        finally:
            port.read = read
            elapsed = time.monotonic() - started_at
            size = "exact" if received == resp_len_exp else "short" if received < resp_len_exp else "extra"
            if not received:
                size = "empty"
            log(
                f"MagicPy {command}: {elapsed:.3f} s, expected {resp_len_exp} bytes, "
                f"received {received} bytes ({size}), result={result}",
                "DEBUG",
            )

    def get_pulse_settings(self):
        """Read the complete command-09 settings without changing device state.

        Unlike get_waveform() in MagicPy 0.1.6, this does not reconnect the
        serial port. Return the original response/error tuple for validation.
        """
        if self.flush_before_cmd:
            self.flush_input()
        return self.process_command(
            "0B", ["09", "00"] + ["00"] * 9,
            get_response=True, resp_len_exp=14,
        )


class PairedPulseMagVenture(MagVenture):
    """Encode 1–200 ms IPIs; device resolution is checked by the controller."""

    def parse_ipi(self, ipi):
        ticks = ipi_ticks(ipi)
        # Encode exact integer ticks, avoiding hexlm's float truncation.
        encoded = f"{ticks:04x}"
        return encoded[2:4], encoded[0:2]
