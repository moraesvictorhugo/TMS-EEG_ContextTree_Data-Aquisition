"""
MagVenture stimulator controller.

Wraps the magicpy library to provide a cleaner interface for the
experiment loop, encapsulating connection, mode setup, arming, and firing.
"""
import time

import magicpy as mp


class StimulatorController:
    """High-level controller for a MagVenture TMS stimulator.

    Parameters
    ----------
    port : str
        Serial port the stimulator is connected to (e.g. ``"COM1"``).
    """

    def __init__(self, port):
        self._port = port
        self._stimulator = None

    # ── connection ────────────────────────────────────────────────────
    def connect(self):
        """List serial ports, wait for user confirmation, and connect."""
        mp.list_serial_ports()
        input(
            "Portas listadas. Certifique-se de que está conectando "
            "na porta correta. Pressione Enter para continuar..."
        )
        self._stimulator = mp.MagVenture(self._port)
        self._stimulator.connect()
        self._stimulator.set_page("Main", get_response=False)

    # ── pulse preparation ─────────────────────────────────────────────
    def prepare_pulse(self, intensity_value):
        """Configure the stimulator mode, arm it, and set amplitude.

        Parameters
        ----------
        intensity_value : int
            Target intensity in % MSO.
        """
        self._stimulator.set_mode(
            mode="Standard",
            current_dir="Normal",
            n_pulses_per_burst=2,
            ipi=10,
            baratio=80,
        )
        time.sleep(1)
        self._stimulator.arm(get_response=False)
        time.sleep(1)
        self._stimulator.set_amplitude(intensity_value, b_amp=None)
        time.sleep(1)

    # ── firing ────────────────────────────────────────────────────────
    def fire(self):
        """Fire a single TMS pulse."""
        self._stimulator.fire()

    # ── context manager ───────────────────────────────────────────────
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # magicpy doesn't expose an explicit disconnect, but if it did
        # we would call it here.
        pass
