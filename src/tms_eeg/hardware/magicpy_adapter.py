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

    _recover_status_with_didt = True

    def process_command(self, command_length, command_bytes, resp_len_exp=8, get_response=False):
        process = super().process_command
        trace = bool(get_response and config.ENABLE_LOGGING)
        recover_status = (
            self._recover_status_with_didt
            and (command_length, command_bytes, resp_len_exp, get_response) == ("01", "00", 13, 3)
        )
        if not trace and not recover_status:
            return process(command_length, command_bytes, resp_len_exp, get_response)

        # Observe the inherited transaction. The acquisition loop owns the port.
        port = self.port
        read = port.read
        received = 0
        packet = bytearray()

        def read_and_count(*args, **kwargs):
            nonlocal received
            data = read(*args, **kwargs)
            received += len(data)
            if recover_status:
                packet.extend(data)
            return data

        parts = [command_bytes] if isinstance(command_bytes, str) else command_bytes
        command = " ".join(parts[:2])
        started_at = time.monotonic()
        port.read = read_and_count
        result = "exception"
        try:
            response, error = process(command_length, command_bytes, resp_len_exp, get_response)
            if recover_status and error == 1:
                status = self._status_from_mixed_reply(packet, response)
                if status is not None:
                    response, error = status, 0
                    log("MagicPy status recovered from a reply containing a di/dt frame.", "DEBUG")
            result = f"{type(response).__name__}, error={error!r}"
            if isinstance(response, str):
                result = f"{response!r}, error={error!r}"
            return response, error
        finally:
            port.read = read
            if trace:
                elapsed = time.monotonic() - started_at
                size = "exact" if received == resp_len_exp else "short" if received < resp_len_exp else "extra"
                if not received:
                    size = "empty"
                log(
                    f"MagicPy {command}: {elapsed:.3f} s, expected {resp_len_exp} bytes, "
                    f"received {received} bytes ({size}), result={result}",
                    "DEBUG",
                )

    def _status_from_mixed_reply(self, packet, response):
        """Accept one complete status frame accompanied by one di/dt frame."""
        if len(packet) != 21 or not isinstance(response, list) or len(response) != 2:
            return None

        status_header = b"\xfe\x09\x00"
        didt_header = b"\xfe\x04\x02"
        if packet.startswith(didt_header):
            didt, status = packet[:8], packet[8:]
            didt_data, status_data = response
        else:
            status, didt = packet[:13], packet[13:]
            status_data, didt_data = response
        if not isinstance(status_data, dict) or didt_data is not None:
            return None

        for frame, header in ((status, status_header), (didt, didt_header)):
            if not frame.startswith(header) or frame[-1] != 0xff:
                return None
            checksum = self.calc_crc([f"{byte:02x}" for byte in frame[2:-2]])
            if int(checksum, 16) != frame[-2]:
                return None
        return status_data

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

    _recover_status_with_didt = False

    def parse_ipi(self, ipi):
        ticks = ipi_ticks(ipi)
        # Encode exact integer ticks, avoiding hexlm's float truncation.
        encoded = f"{ticks:04x}"
        return encoded[2:4], encoded[0:2]
