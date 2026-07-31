"""
ESP32 trigger sender via serial.

Sends integer trigger values (1–15) to an ESP32 microcontroller,
which outputs them as a 4-bit binary code for the EEG acquisition system.
"""
import time

import serial


class TriggerSender:
    """Serial connection to the ESP32 trigger board.

    Parameters
    ----------
    port : str
        Serial port (e.g. ``"COM3"`` or ``"/dev/ttyUSB0"``).
    baud_rate : int
        Baud rate matching the ESP32 firmware (default 115200).
    startup_delay : float
        Seconds to wait after opening the port for the ESP32 to reboot.
    """

    def __init__(self, port, baud_rate=115200, startup_delay=2):
        self._ser = serial.Serial()
        self._ser.port = port
        self._ser.baudrate = baud_rate
        self._ser.timeout = 1
        # Explicitly disable DTR and RTS to prevent auto-resetting the ESP32
        self._ser.setDTR(False)
        self._ser.setRTS(False)
        self._ser.open()
        time.sleep(startup_delay)  # wait for ESP32 to reboot, if it still does

    def send(self, trigger_value):
        """Send a trigger value to the ESP32.

        Parameters
        ----------
        trigger_value : int
            Trigger code, must be between 1 and 15 inclusive.
        """
        if 1 <= trigger_value <= 15:
            self._ser.write(f"{trigger_value}\n".encode("ascii"))
            self._ser.flush()
            print(f"Trigger enviado: {trigger_value}")
        else:
            print(f"Trigger inválido (não enviado): {trigger_value}")

    def close(self):
        """Close the serial connection."""
        try:
            self._ser.close()
        except Exception:
            pass

    # ── context manager ───────────────────────────────────────────────
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
