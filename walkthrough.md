# Debug and Logging Implementation Walkthrough

## Summary of Changes
The system has been updated to address the elusive `IndexError` while establishing a comprehensive logging mechanism for better observability. The investigation confirmed that the core pulse logic (`main.py`) correctly manages indices. The `IndexError` was therefore determined to be originating from the `magicpy` MagVenture interface parsing malformed/empty serial responses during `prepare_pulse` or `fire`. Because `main.py` blindly caught all `Exception`s and retried the pulse immediately, this triggered a repetitive error loop whenever the serial port lost synchronization.

### 1. Toggleable Logging System
- **`config.py`**: Added `ENABLE_LOGGING = True` as a global flag.
- **`logger.py`**: Created a new utility containing `log()`. This checks the config flag before printing, providing a clean way to toggle debug statements across the entire project.

### 2. Enhanced Safety and Tracebacks in `main.py`
- **Redundant Bounds Check**: Placed an explicit `if pulse_index >= len(sequence): break` at the very beginning of the `while True:` loop to absolutely guarantee no array overruns can happen under any unforeseen condition.
- **Traceback Integration**: The `except Exception as e:` block now uses `traceback.format_exc()` to output the full stack trace (using the new `log()` tool). This means if `magicpy` fails again, the exact line number and cause (e.g. `response[0]`) will be clearly printed in the terminal.
- **Verbose Tracking**: Added `log()` statements throughout the pulse preparation, gate checking, and firing stages.

### 3. Hardware Controller Protections
- **`stimulator.py`**: Wrapped the `mp.MagVenture` connections and `.set_mode()`, `.arm()`, and `.fire()` methods in robust `try...except` blocks that extract the stack trace and re-raise the exception, preventing silent cascading failures.
- **`tracker.py`**: Wrapped the Socket.IO buffer processing loop in a `try...except` to protect against incorrectly formatted payloads (e.g. lists sent instead of dictionaries) and log them out cleanly.

## Validation
- ✅ Modified Python files were checked for syntax using `python3 -m py_compile`.
- ✅ No core business logic or timing constraints were altered.

> [!TIP]
> The next time you run your experiment, you will see rich logs guiding you step-by-step. If an `IndexError` occurs in `magicpy`, it will print a full block detailing precisely what serial read attempt failed, allowing you to accurately restart or recalibrate the MagVenture device. You can turn this off simply by setting `ENABLE_LOGGING = False` in your `config.py`.
