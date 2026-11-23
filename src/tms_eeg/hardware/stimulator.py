"""
MagVenture stimulator controller.

Wraps the magicpy library to provide a cleaner interface for the
experiment loop, encapsulating connection, mode setup, arming, and firing.
"""
import time
import traceback

import magicpy as mp
from tms_eeg import config
from tms_eeg.logger import log
from tms_eeg.hardware.magicpy_adapter import MagVenture, PairedPulseMagVenture, ipi_ticks


NON_BURST_WAVEFORMS = ("Monophasic", "Biphasic", "HalfSine")


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
    if waveform not in NON_BURST_WAVEFORMS:
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
        self._arm_was_confirmed = False
        self._last_profile = None

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
            device_class = PairedPulseMagVenture if self._paired_pulse else MagVenture
            self._stimulator = device_class(self._port, wait_s=config.MAGVENTURE_RESPONSE_DELAY)
            self._stimulator.connect()
            self._stimulator.set_page("Main", get_response=False)
            log("Connected to MagVenture successfully.", "INFO")
        except Exception as e:
            log(f"Failed to connect to MagVenture:\n{traceback.format_exc()}", "ERROR")
            raise

    # ── pulse preparation ─────────────────────────────────────────────
    def _profile_is_current(self, mode, waveform, ipi, a_intensity, b_intensity):
        """Require live settings and amplitude readback before reusing a profile."""
        try:
            settings = _checked(self._stimulator.get_pulse_settings(), "repeat settings")
            if not isinstance(settings, dict):
                raise RuntimeError("Pulse settings readback is not a single response.")
            actual_waveform = settings.get("Waveform")
            if (
                settings.get("Mode") != mode
                or settings.get("CurrentDirection") != "Normal"
                or actual_waveform not in NON_BURST_WAVEFORMS
                or (waveform is not None and actual_waveform != waveform)
                or ipi_ticks(settings.get("IPIvalue")) != ipi_ticks(ipi)
            ):
                raise RuntimeError(f"Pulse settings changed: {settings!r}")

            status = _checked(self._stimulator.get_status(), "repeat status")
            expected = {
                "Status": "Enabled", "Mode": mode, "Waveform": actual_waveform,
                "amplitudePercentage_A": a_intensity,
            }
            if b_intensity is not None:
                expected["amplitudePercentage_B"] = b_intensity
            if not isinstance(status, dict) or any(
                status.get(key) != value for key, value in expected.items()
            ):
                raise RuntimeError(f"Stimulator status changed: {status!r}")
        except Exception as error:
            log(f"Repeated profile could not be confirmed. Preparing again: {error}", "INFO")
            return False
        log("Repeated profile confirmed by current settings and status.", "INFO")
        return True

    def prepare_pulse(self, intensity_value):
        """Configure the stimulator mode, arm it, and set amplitude.

        Parameters
        ----------
        intensity_value : int
            Target intensity in % MSO.
        """
        previous = self._last_profile
        self._last_profile = None
        requested = ("Standard", None, 10, intensity_value, None)
        if requested == previous and self._profile_is_current(*requested):
            self._last_profile = requested
            return

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
            self._last_profile = requested
        except Exception as e:
            log(f"Error in prepare_pulse:\n{traceback.format_exc()}", "ERROR")
            raise

    def _checked_settings_command(self, result, operation, mode, ipi, waveform=None):
        """Recover a missing set acknowledgement only from matching fresh settings."""
        try:
            return _checked(result, operation)
        except RuntimeError as command_error:
            log(f"{command_error}. Reading settings for confirmation.", "DEBUG")
            try:
                response = _checked(
                    self._stimulator.get_pulse_settings(), f"readback after {operation}"
                )
                expected = {"Mode": mode, "CurrentDirection": "Normal"}
                if waveform is not None:
                    expected["Waveform"] = waveform
                if (not isinstance(response, dict)
                        or any(response.get(key) != value for key, value in expected.items())
                        or ipi_ticks(response.get("IPIvalue")) != ipi_ticks(ipi)):
                    raise RuntimeError(
                        f"Requested settings not confirmed: expected {expected!r}, "
                        f"IPI={ipi!r} ms; received {response!r}"
                    )
            except Exception as readback_error:
                raise RuntimeError(
                    f"{command_error}; independent settings check failed: {readback_error}"
                ) from readback_error
            log(f"{operation} confirmed by independent settings readback.", "INFO")
            return response

    def _arm_confirmed(self):
        """Confirm enable, including a repeated arm with no acknowledgement.

        Enabled is a device state, not a guarantee that the coil is charged
        or that a subsequent fire command physically delivers a pulse.
        """
        try:
            _checked(self._stimulator.arm(get_response=True), "arm")
        except RuntimeError as command_error:
            # Some devices do not send a new acknowledgement when already
            # enabled. Do not infer that state from previous pulses or an
            # error payload: ask the device again.
            try:
                status = _checked(self._stimulator.get_status(), "get_status after arm")
                if not isinstance(status, dict) or status.get("Status") != "Enabled":
                    raise RuntimeError(f"Enabled state not confirmed: {status!r}")
            except Exception as status_error:
                raise RuntimeError(
                    f"{command_error}; independent arm status check failed: {status_error}"
                ) from status_error
            log("Arm confirmed by independent Enabled status readback.", "INFO")

    def prepare_stimulus(self, profile):
        """Prepare one Standard/Dual event; never synthesize A/B timing in Python."""
        self._prepared = False
        previous = self._last_profile
        self._last_profile = None
        check_enabled = self._arm_was_confirmed
        self._arm_was_confirmed = False
        if not self._paired_pulse:
            raise RuntimeError("Pulse profiles require the paired-pulse controller.")
        validate_profile(profile)
        if self._waveform not in NON_BURST_WAVEFORMS:
            raise ValueError("Unsupported non-burst waveform.")
        mode = "Dual" if profile["type"] == "paired" else "Standard"
        ipi = profile.get("ipi_ms", 10)
        requested = (mode, self._waveform, ipi, profile["a_intensity"], profile.get("b_intensity"))
        if requested == previous and self._profile_is_current(*requested):
            self._last_profile = requested
            self._arm_was_confirmed = True
            self._prepared = True
            return

        settings = dict(current_dir="Normal", n_pulses_per_burst=2,
                        ipi=ipi, baratio=1, get_response=True)
        log(f"Preparing requested pulse profile: {profile}; waveform={self._waveform}", "INFO")
        self._checked_settings_command(
            self._stimulator.set_mode(mode=mode, **settings), "set_mode", mode, ipi
        )
        response = self._checked_settings_command(
            self._stimulator.set_waveform(self._waveform, **settings),
            "set_waveform", mode, ipi, waveform=self._waveform,
        )
        if not isinstance(response, dict) or any(
            response.get(key) != expected
            for key, expected in (("Mode", mode), ("Waveform", self._waveform),
                                  ("CurrentDirection", "Normal"))
        ):
            raise RuntimeError(f"Stimulator mode/waveform readback mismatch: {response!r}")
        time.sleep(1)
        already_enabled = False
        if check_enabled:
            status, error = self._stimulator.get_status()
            already_enabled = (
                error == 0 and isinstance(status, dict) and status.get("Status") == "Enabled"
            )
        if not already_enabled:
            self._arm_confirmed()
            time.sleep(1)
        _checked(self._stimulator.set_amplitude(
            profile["a_intensity"], b_amp=profile.get("b_intensity"), get_response=True
        ), "set_amplitude")
        time.sleep(1)
        actual_mode = _checked(self._stimulator.get_mode(), "get_mode")
        actual_ipi = _checked(self._stimulator.get_ipi(), "get_ipi")
        if actual_mode != mode or ipi_ticks(actual_ipi) != ipi_ticks(ipi):
            raise RuntimeError(f"Stimulator mode/IPI readback mismatch: {actual_mode!r}, {actual_ipi!r}")
        self._last_profile = requested
        self._arm_was_confirmed = True
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
            self._arm_was_confirmed = False
            self._last_profile = None
            log(f"Error in fire():\n{traceback.format_exc()}", "ERROR")
            raise

    # ── context manager ───────────────────────────────────────────────
    def disarm(self):
        """Require disable acknowledgement or a fresh, successful disabled readback."""
        self._prepared = False
        self._arm_was_confirmed = False
        self._last_profile = None
        if self._stimulator is not None:
            try:
                result = self._stimulator.disarm(get_response=True)
                try:
                    _checked(result, "disarm")
                except RuntimeError as command_error:
                    # MagicPy 0.1.6 assumes an 8-byte disable reply. X100
                    # replies may contain multiple messages, and disabling an
                    # already disabled device may return Empty. Never accept
                    # those error payloads as proof: query the device afresh.
                    try:
                        status = _checked(self._stimulator.get_status(), "get_status after disarm")
                        if not isinstance(status, dict) or status.get("Status") != "Disabled":
                            raise RuntimeError(f"Disabled state not confirmed: {status!r}")
                    except Exception as status_error:
                        raise RuntimeError(
                            f"{command_error}; independent status check failed: {status_error}"
                        ) from status_error
                    log("Disarm confirmed by independent Disabled status readback.", "INFO")
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
