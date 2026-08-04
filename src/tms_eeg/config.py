"""
Experiment configuration — single source of truth for all parameters.

Edit the values below before each experiment session.
"""

# ─── Experiment protocol ──────────────────────────────────────────────
MODE = "intensity"            # protocol type (currently only "intensity")
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

# ─── Sequence generation ─────────────────────────────────────────────
ALPHABET = [0, 1, 2]          # possible stimulus types
NUMBER_OF_STIMULI = 400       # total number of trials

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
