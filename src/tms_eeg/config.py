"""
Experiment configuration — single source of truth for all parameters.

Edit the values below before each experiment session.
"""

# ─── Experiment protocol ──────────────────────────────────────────────
MODE = "intensity"            # "intensity" (legacy) or "paired-pulse"
VOLUNTEER_CODE = "V00"        # volunteer identifier
EXPORT_SEQUENCE_TXT = False   # whether to save the generated sequence to a .txt file

# ─── Volunteer's motor threshold ──────────────────────────────────────
RMT_INTENSITY = 10            # resting motor threshold (% MSO)

# Derived intensity levels (computed from RMT_INTENSITY)
INTENSITY_0 = int(0.8 * RMT_INTENSITY)   # 80% rMT
INTENSITY_1 = int(RMT_INTENSITY)         # 100% rMT
INTENSITY_2 = int(1.2 * RMT_INTENSITY)   # 120% rMT

# Map sequence symbols → intensity values (actual % MSO, not strings)
INTENSITY_MAP = {
    0: INTENSITY_0,
    1: INTENSITY_1,
    2: INTENSITY_2,
}

# ─── Simple/paired protocol (used only with MODE = "paired-pulse") ────
# EXAMPLE settings, not a validated experimental prescription. Intensities
# are integer % MSO. Confirm device/firmware Dual support and measure A/B timing.
# A = conditioning pulse, B = test pulse. IPI is onset A to onset B in ms.
# Labels are arbitrary: e.g. rename paired_1/paired_2 to SICI/LICI. They do not
# select a protocol automatically. Software IPI range: 1–200 ms; verify readback.
PULSE_WAVEFORM = "Biphasic"    # "Monophasic", "Biphasic" or "HalfSine"; no burst
PULSE_MAP = {
    0: {"label": "single", "type": "single", "a_intensity": INTENSITY_2},
    1: {
        "label": "paired_1", "type": "paired",
        "a_intensity": INTENSITY_0, "b_intensity": INTENSITY_2, "ipi_ms": 2.0,
    },
    2: {
        "label": "paired_2", "type": "paired",
        "a_intensity": INTENSITY_0, "b_intensity": INTENSITY_2, "ipi_ms": 2.0,
    },
}

# ─── Sequence generation ─────────────────────────────────────────────
SEQUENCE_ALGORITHM = "constant"  # "context tree", "pseudo-random" or "constant"
ALPHABET = [1]          # possible stimulus types; constant requires one, e.g. [2]
NUMBER_OF_STIMULI = 100       # total number of trials
NUMBER_OF_BLOCKS = 1          # equal blocks; total must be divisible; G resumes

# ─── Timing ──────────────────────────────────────────────────────────
ITI = (1, 3)                  # inter-trial interval range in seconds
                              # MagicPy already adds ~3 s due to sleep calls

# ─── Target tracking ─────────────────────────────────────────────────
TARGET_HISTORY_SIZE = 50      # how many consecutive True statuses are needed
                              # before firing a pulse

# ─── Neuronavigation (InVesalius relay server) ────────────────────────
NAVIGATION_ADDRESS = "127.0.0.1"
NAVIGATION_PORTS = [5000]
CREATE_NAVIGATION_MARKER = False

# Publisher message topics expected from InVesalius
PUB_MESSAGES = [
    "Coil at target",
    "Marker label",
]

# ─── MagVenture stimulator ───────────────────────────────────────────
MAGVENTURE_PORT = "COM1"

# ─── ESP32 trigger ───────────────────────────────────────────────────
ESP32_SERIAL_PORT = "COM3"
ESP32_BAUD_RATE = 115200
ESP32_STARTUP_DELAY = 2       # seconds to wait for ESP32 reboot after serial open

# ─── Debug and Logging ───────────────────────────────────────────────
ENABLE_LOGGING = False         # Toggle to enable verbose print statements
