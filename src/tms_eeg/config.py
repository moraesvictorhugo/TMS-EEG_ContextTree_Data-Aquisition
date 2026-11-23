"""Settings to review before each experiment session."""

# ─── Session and design ──────────────────────────────────────────────
VOLUNTEER_CODE = "V00"
MODE = "intensity"  # "intensity" or "paired-pulse"
SEQUENCE_ALGORITHM = "context tree"  # "context tree", "pseudo-random", or "constant"
# Context tree uses this for its first symbol. Pseudo-random uses it throughout.
ALPHABET = [0, 1, 2]  # Constant requires one symbol.
NUMBER_OF_STIMULI = 400  # Total trials. Each pair counts as one.
NUMBER_OF_BLOCKS = 2  # Equal blocks. Trial count must divide evenly.
ITI = (4, 6)  # Random start-to-start range (s). Pairs start at pulse A.
EXPORT_SEQUENCE_TXT = False

# ─── Motor threshold and intensities ─────────────────────────────────
RMT_INTENSITY = 20  # Resting motor threshold (% MSO).

# Derived from rMT in integer % MSO.
INTENSITY_0 = int(0.8 * RMT_INTENSITY)
INTENSITY_1 = int(RMT_INTENSITY)
INTENSITY_2 = int(1.2 * RMT_INTENSITY)

# Symbol to intensity in "intensity" mode.
INTENSITY_MAP = {
    0: INTENSITY_0,
    1: INTENSITY_1,
    2: INTENSITY_2,
}

# ─── Pulse profiles ("paired-pulse" mode) ─────────────────────────────
PULSE_WAVEFORM = "Biphasic"  # "Monophasic", "Biphasic", or "HalfSine".
# Example profiles. Confirm Dual support, readback, and pulse timing.
# A is the conditioning pulse, B the test pulse. IPI is A-to-B onset (ms).
# Amplitudes are integer % MSO. Labels are descriptive.
PULSE_MAP = {
    0: {"label": "single", "type": "single", "a_intensity": INTENSITY_2},
    1: {
        "label": "paired_1", "type": "paired",
        "a_intensity": INTENSITY_2, "b_intensity": INTENSITY_2, "ipi_ms": 100.0,
    },
    2: {
        "label": "paired_2", "type": "paired",
        "a_intensity": INTENSITY_0, "b_intensity": INTENSITY_2, "ipi_ms": 2.0,
    },
}

# ─── Neuronavigation and targeting (InVesalius) ───────────────────────
NAVIGATION_ADDRESS = "127.0.0.1"
NAVIGATION_PORTS = [5000]
TARGET_HISTORY_SIZE = 50  # Consecutive on-target checks before preparation.
CREATE_NAVIGATION_MARKER = False

# Topic order: target status, marker label.
PUB_MESSAGES = ["Coil at target", "Marker label"]

# ─── Equipment communication ─────────────────────────────────────────
# MagVenture
MAGVENTURE_PORT = "COM1"
MAGVENTURE_RESPONSE_DELAY = 0.05  # Delay before MagicPy reads a reply (s).

# ESP32 trigger
ESP32_SERIAL_PORT = "COM3"
ESP32_BAUD_RATE = 115200
ESP32_STARTUP_DELAY = 2  # Reboot wait after opening the port (s).

# ─── Diagnostics ─────────────────────────────────────────────────────
ENABLE_LOGGING = True
