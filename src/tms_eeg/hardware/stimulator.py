"""
MagVenture stimulator controller.

Wraps the magicpy library to provide a cleaner interface for the
experiment loop, encapsulating connection, mode setup, arming, and firing.
"""
import time
import traceback

import magicpy as mp
from tms_eeg.logger import log
from tms_eeg.hardware.magicpy_adapter import PairedPulseMagVenture, ipi_ticks


def validate_profile(profile):
    """Reject invalid settings before issuing any device commands."""
    if not isinstance(profile, dict):
        raise ValueError("Each pulse profile must be a dictionary.")
    if profile.get("type") not in ("single", "paired"):
        raise ValueError("Pulse type must be 'single' or 'paired'.")
    if not isinstance(profile.get("label"), str) or not profile["label"].strip():
        raise ValueError("Each pulse profile needs a nonempty label.")
    fields = ["a_intensity"]
    if profile["type"] == "paired":
        fields.append("b_intensity")
        ipi_ticks(profile.get("ipi_ms"))
    elif "b_intensity" in profile or "ipi_ms" in profile:
        raise ValueError("Single pulses must not specify B intensity or IPI.")
    for field in fields:
        value = profile.get(field)
        if type(value) is not int or not 0 <= value <= 100:
            raise ValueError(f"{field} must be an integer between 0 and 100 % MSO.")


def validate_protocol(mode, alphabet, pulse_map, waveform):
    """Validate the opt-in protocol without connecting any subsystem."""
    if mode not in ("intensity", "paired-pulse"):
        raise ValueError(f"Unknown MODE: {mode!r}")
    if mode == "intensity":
        return
    if waveform not in ("Monophasic", "Biphasic", "HalfSine"):
        raise ValueError("PULSE_WAVEFORM must be Monophasic, Biphasic or HalfSine (no burst).")
    if not isinstance(pulse_map, dict) or not alphabet:
        raise ValueError("PULSE_MAP and ALPHABET must be nonempty.")
    for symbol in alphabet:
        if type(symbol) is not int or not 0 <= symbol <= 14:
            raise ValueError("Symbols must be integers 0–14 for EEG triggers 1–15.")
        if symbol not in pulse_map:
            raise ValueError(f"Missing pulse profile for symbol {symbol}.")
        validate_profile(pulse_map[symbol])


def _checked(result, operation):
    """MagicPy reports communication errors in a tuple, not just exceptions."""
    response, error = result
    if error != 0:
        raise RuntimeError(f"MagicPy {operation} failed: {response!r} (error={error!r})")
    return response


class StimulatorController:
    """High-level controller for a MagVenture TMS stimulator.

    Parameters
    ----------
    port : str
        Serial port the stimulator is connected to (e.g. ``"COM1"``).
    paired_pulse : bool, optional
        Opt into the local IPI adapter and profile preparation guard.
    waveform : str, optional
        Explicit non-burst waveform used only for profile preparation.
    """

    def __init__(self, port, paired_pulse=False, waveform="Biphasic"):
        self._port = port
        self._stimulator = None
        self._paired_pulse = paired_pulse
        self._waveform = waveform
        self._prepared = False

    # ── connection ────────────────────────────────────────────────────
    def connect(self):
        """List serial ports, wait for user confirmation, and connect."""
        log("Listing serial ports for MagVenture...", "INFO")
        mp.list_serial_ports()
        input(
            "Portas listadas. Certifique-se de que está conectando "
            "na porta correta. Pressione Enter para continuar..."
        )
        log(f"Connecting to MagVenture on {self._port}...", "INFO")
        try:
            device_class = PairedPulseMagVenture if self._paired_pulse else mp.MagVenture
            self._stimulator = device_class(self._port)
            self._stimulator.connect()
            self._stimulator.set_page("Main", get_response=False)
            log("Connected to MagVenture successfully.", "INFO")
        except Exception as e:
            log(f"Failed to connect to MagVenture:\n{traceback.format_exc()}", "ERROR")
            raise

    # ── pulse preparation ─────────────────────────────────────────────
    def prepare_pulse(self, intensity_value):
        """Configure the stimulator mode, arm it, and set amplitude.

        Parameters
        ----------
        intensity_value : int
            Target intensity in % MSO.
        """
        try:
            log(f"Setting mode with intensity: {intensity_value}", "DEBUG")
            self._stimulator.set_mode(
                mode="Standard",
                current_dir="Normal",
                n_pulses_per_burst=2,
                ipi=10,
                baratio=80,
            )
            time.sleep(1)
            log("Arming stimulator...", "DEBUG")
            self._stimulator.arm(get_response=False)
            time.sleep(1)
            log("Setting amplitude...", "DEBUG")
            self._stimulator.set_amplitude(intensity_value, b_amp=None)
            time.sleep(1)
        except Exception as e:
            log(f"Error in prepare_pulse:\n{traceback.format_exc()}", "ERROR")
            raise

    def prepare_stimulus(self, profile):
        """Prepare one Standard/Dual event; never synthesize A/B timing in Python."""
        self._prepared = False
        if not self._paired_pulse:
            raise RuntimeError("Pulse profiles require the paired-pulse controller.")
        validate_profile(profile)
        if self._waveform not in ("Monophasic", "Biphasic", "HalfSine"):
            raise ValueError("Unsupported non-burst waveform.")
        mode = "Dual" if profile["type"] == "paired" else "Standard"
        ipi = profile.get("ipi_ms", 10)
        settings = dict(current_dir="Normal", n_pulses_per_burst=2,
                        ipi=ipi, baratio=1, get_response=True)
        log(f"Preparing requested pulse profile: {profile}; waveform={self._waveform}", "INFO")
        _checked(self._stimulator.set_mode(mode=mode, **settings), "set_mode")
        response = _checked(
            self._stimulator.set_waveform(self._waveform, **settings), "set_waveform"
        )
        if not isinstance(response, dict) or any(
            response.get(key) != expected
            for key, expected in (("Mode", mode), ("Waveform", self._waveform),
                                  ("CurrentDirection", "Normal"))
        ):
            raise RuntimeError(f"Stimulator mode/waveform readback mismatch: {response!r}")
        time.sleep(1)
        _checked(self._stimulator.arm(get_response=True), "arm")
        time.sleep(1)
        _checked(self._stimulator.set_amplitude(
            profile["a_intensity"], b_amp=profile.get("b_intensity"), get_response=True
        ), "set_amplitude")
        time.sleep(1)
        actual_mode = _checked(self._stimulator.get_mode(), "get_mode")
        actual_ipi = _checked(self._stimulator.get_ipi(), "get_ipi")
        if actual_mode != mode or ipi_ticks(actual_ipi) != ipi_ticks(ipi):
            raise RuntimeError(f"Stimulator mode/IPI readback mismatch: {actual_mode!r}, {actual_ipi!r}")
        self._prepared = True

    # ── firing ────────────────────────────────────────────────────────
    def fire(self):
        """Fire one configured event (one physical pulse or an A/B pair)."""
        if self._paired_pulse:
            if not self._prepared:
                raise RuntimeError("No successfully prepared pulse profile.")
            self._prepared = False
        try:
            log("Sending fire command to MagVenture...", "DEBUG")
            self._stimulator.fire()
            log("Fire command successful.", "DEBUG")
        except Exception as e:
            log(f"Error in fire():\n{traceback.format_exc()}", "ERROR")
            raise

    # ── context manager ───────────────────────────────────────────────
    def disarm(self):
        """Invalidate preparation and require acknowledgement of disable command."""
        self._prepared = False
        if self._stimulator is not None:
            try:
                _checked(self._stimulator.disarm(get_response=True), "disarm")
            except Exception:
                print("WARNING: stimulator disarm was NOT confirmed. Check the device physically.")
                raise

    def close(self):
        """Attempt disarm and disconnect independently; never hide cleanup errors."""
        try:
            self.disarm()
        except Exception as error:
            print(f"WARNING: disarm during cleanup failed: {error}")
        finally:
            if self._stimulator is not None:
                try:
                    self._stimulator.disconnect()
                except Exception as error:
                    print(f"WARNING: stimulator disconnect failed: {error}")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
