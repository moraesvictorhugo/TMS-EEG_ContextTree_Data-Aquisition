"""
TMS-EEG ContextTree Data Acquisition — experiment entry point.

This script orchestrates the full experiment:
  1. Generate a context-tree stimulus sequence
  2. Connect to neuronavigation, stimulator, and trigger board
  3. Run the experiment loop with pause/resume support
"""
import random
import time
import traceback
from collections import deque
import keyboard
from tms_eeg import config
from tms_eeg.sequence import generate_sequence, print_sequence_stats, export_sequence
from tms_eeg.hardware.stimulator import StimulatorController
from tms_eeg.hardware.trigger import TriggerSender
from tms_eeg.navigation.tracker import NavigationTracker
from tms_eeg.logger import log


def wait_for_key(key, prompt):
    """Block until the user presses the given key.

    Parameters
    ----------
    key : str
        Key name (e.g. ``"s"``).
    prompt : str
        Message shown to the user while waiting.
    """
    print(prompt)
    while True:
        if keyboard.is_pressed(key):
            break


def run_experiment(sequence, tracker, stimulator, trigger):
    """Execute the main experiment loop.

    Fires TMS pulses according to *sequence*, gated by neuronavigation
    target tracking.  Supports pause (B key) and resume (G key).

    Parameters
    ----------
    sequence : list[int]
        Stimulus sequence (each element in {0, 1, 2}).
    tracker : NavigationTracker
        Connected neuronavigation tracker.
    stimulator : StimulatorController
        Connected MagVenture stimulator.
    trigger : TriggerSender
        Connected ESP32 trigger sender.
    """
    target_history = deque(
        [False] * config.TARGET_HISTORY_SIZE,
        maxlen=config.TARGET_HISTORY_SIZE,
    )

    pulse_index = 0
    paused = False

    while True:
        # ── safety bounds check ───────────────────────────────────────
        if pulse_index >= len(sequence):
            log(f"Safety bounds check: pulse_index ({pulse_index}) >= sequence length ({len(sequence)}). Breaking loop.", "DEBUG")
            break

        # ── pause / resume ────────────────────────────────────────────
        if keyboard.is_pressed("b"):
            paused = True
            log("Paused sequence (key B).", "INFO")
            print("Paused sequence (key B).")
        if keyboard.is_pressed("g") and paused:
            paused = False
            log("Sequence resumed (key G).", "INFO")
            print("Sequence resumed (key G).")

        if paused:
            time.sleep(0.05)
            continue

        # ── target tracking gate ──────────────────────────────────────
        current_status = tracker.all_target_status
        target_history.append(current_status)

        if not all(target_history):
            time.sleep(0.01)
            continue
        
        log(f"Target tracking passed. Preparing to fire pulse {pulse_index + 1}.", "DEBUG")

        # ── fire pulse ────────────────────────────────────────────────
        try:
            stimulus = sequence[pulse_index]
            intensity = config.INTENSITY_MAP[stimulus]
            log(f"Sequence requested stimulus: {stimulus}, Intensity mapping: {intensity}", "DEBUG")
            print(f"Intensity: {intensity} (event {stimulus})")

            log("Calling stimulator.prepare_pulse()", "DEBUG")
            stimulator.prepare_pulse(intensity)
            log("Stimulator armed successfully.", "DEBUG")

            with tracker.status_lock:
                if not tracker.all_target_status:
                    log("Coil moved out of target right before firing. Restarting gate.", "WARNING")
                    print("⚠️ Coil out of target. Restarting gate...")
                    target_history.clear()
                    target_history.extend([False] * config.TARGET_HISTORY_SIZE)
                    continue

                log("Calling stimulator.fire()", "DEBUG")
                stimulator.fire()
                # trigger for EEG: 0→1, 1→2, 2→3
                log(f"Sending trigger value: {stimulus + 1}", "DEBUG")
                trigger.send(stimulus + 1)

            print("Firing")
            time.sleep(random.uniform(*config.ITI))

            print(f"Pulse index: {pulse_index + 1}")
            log(f"Pulse index {pulse_index} successfully fired.", "INFO")
            pulse_index += 1

        except Exception as e:
            error_details = traceback.format_exc()
            log(f"Exception during pulse firing:\n{error_details}", "ERROR")
            print(f"\n⚠️ ERRO in pulse {pulse_index}: {e}")
            print("Trying again the same pulse...\n")
            time.sleep(2)

        # ── end condition ─────────────────────────────────────────────
        if pulse_index >= len(sequence):
            print("Ending sequence (end of pulse sequence).")
            break

        time.sleep(0.01)


def main():
    """Set up all subsystems and run the experiment."""

    # 1. Sequence generation
    sequence = generate_sequence(config.NUMBER_OF_STIMULI, config.ALPHABET)
    print_sequence_stats(sequence)

    if config.EXPORT_SEQUENCE_TXT:
        export_sequence(
            sequence,
            config.NUMBER_OF_STIMULI,
            config.VOLUNTEER_CODE,
        )

    # 2. Connect neuronavigation
    tracker = NavigationTracker()
    tracker.connect(config.NAVIGATION_ADDRESS, config.NAVIGATION_PORTS)

    # 3. Connect stimulator
    stimulator = StimulatorController(config.MAGVENTURE_PORT)
    stimulator.connect()

    # 4. Connect ESP32 trigger
    trigger = TriggerSender(
        config.ESP32_SERIAL_PORT,
        config.ESP32_BAUD_RATE,
        config.ESP32_STARTUP_DELAY,
    )

    # 5. Wait for operator
    wait_for_key("s", "Press the 's' key to start the pulses....")
    print("start sequence")

    # 6. Run experiment
    try:
        run_experiment(sequence, tracker, stimulator, trigger)
    finally:
        trigger.close()
        tracker.stop()


if __name__ == "__main__":
    main()
