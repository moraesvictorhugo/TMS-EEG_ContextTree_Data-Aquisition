# Debug and Implementation Plan: IndexError and Configurable Logging

## 1. Analysis of the `IndexError: list index out of range`

### Por que isso acontece? (Why it happens)
Upon a comprehensive review of the codebase (specifically `main.py`, `sequence.py`, `tracker.py`, and the hardware controllers), the native Python logic correctly bounds all list accesses. The `pulse_index` is strictly checked against `len(sequence)` at the end of every loop iteration, and `pulse_index += 1` only occurs at the very end of the `try` block.

Therefore, the `IndexError` is not originating from the main loop logic itself, but from one of two external boundaries:
1. **MagVenture Serial Communication (`magicpy`)**: If the stimulator device times out or sends a corrupted/empty response, the underlying `magicpy` library attempts to parse it (e.g., splitting a string and accessing `response[0]`). Because `main.py` catches all general `Exception`s and retries the same pulse, it can get stuck in an infinite loop of `IndexError`s if the stimulator enters a bad state.
2. **InVesalius Buffer Processing**: If the `Socket.IO` relay server sends a payload format that differs from the expected dictionary structure (e.g., sending a list instead of a dict), list indexing operations internally might fail.

### Quando isso acontece? (When it happens)
- **During Pulse Preparation/Firing**: When `stimulator.prepare_pulse()` or `stimulator.fire()` is executed and there is a desynchronization in the serial communication with the MagVenture device.
- **During Gate Restart**: If the tracking gate rapidly restarts and causes a race condition in how external hardware states are polled.

## 2. Proposed Changes

### [NEW] Configuration Flag in `config.py`
Add a new flag to control verbose logging across the system.
#### [MODIFY] `src/tms_eeg/config.py`
```python
# ─── Debug and Logging ───────────────────────────────────────────────
ENABLE_LOGGING = True         # Toggle to enable verbose print statements
```

### [NEW] Logging Utility
Create a simple logging function that respects the config flag.
#### [NEW] `src/tms_eeg/logger.py`
```python
from tms_eeg import config

def log(message, level="INFO"):
    """Print the message only if logging is enabled in config."""
    if getattr(config, "ENABLE_LOGGING", False):
        print(f"[{level}] {message}")
```

### [MODIFY] `src/tms_eeg/main.py`
1. **Safety Bound**: Add a redundant safety check for `pulse_index >= len(sequence)` at the very top of the `while True:` loop to absolutely guarantee no out-of-bounds access.
2. **Exception Filtering**: Log the full traceback when an exception occurs in the pulse loop so we can exactly trace the `IndexError`.
3. **Integration of Logs**: Insert `log()` calls at key state transitions (gate checks, pulse preparation, firing).

### [MODIFY] `src/tms_eeg/navigation/tracker.py`
Add logging to the buffer processing to track the state of incoming messages and catch malformed payloads.

### [MODIFY] `src/tms_eeg/hardware/stimulator.py`
Add try-except wrappers and logging around `magicpy` calls to provide detailed context if it throws an `IndexError`.

## User Review Required
> [!IMPORTANT]
> The `IndexError` is highly likely originating from the `magicpy` library due to serial communication issues with the stimulator. By implementing the detailed logging proposed below, the next time the error occurs, the terminal will print exactly which hardware call failed. Do you approve of this logging approach and the addition of `logger.py`?
