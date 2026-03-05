"""
TMS-EEG ContextTree Data Acquisition — experiment entry point.

This script orchestrates the full experiment:
  1. Generate a context-tree stimulus sequence
  2. Connect to neuronavigation, stimulator, and trigger board
  3. Run the experiment loop with pause/resume support
"""
import random
import time
from collections import deque
import keyboard
from tms_eeg import config
from tms_eeg.sequence import generate_sequence, print_sequence_stats, export_sequence
from tms_eeg.hardware.stimulator import StimulatorController
from tms_eeg.hardware.trigger import TriggerSender
from tms_eeg.navigation.tracker import NavigationTracker


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
        # ── pause / resume ────────────────────────────────────────────
        if keyboard.is_pressed("b"):
            paused = True
            print("Sequência pausada (tecla B).")
        if keyboard.is_pressed("g") and paused:
            paused = False
            print("Sequência retomada (tecla G).")

        if paused:
            time.sleep(0.05)
            continue

        # ── target tracking gate ──────────────────────────────────────
        current_status = tracker.target_status
        target_history.append(current_status)

        if not all(target_history):
            time.sleep(0.01)
            continue

        # ── fire pulse ────────────────────────────────────────────────
        try:
            stimulus = sequence[pulse_index]
            intensity = config.INTENSITY_MAP[stimulus]
            print(f"Intensidade: {intensity} (tipo {stimulus})")

            stimulator.prepare_pulse(intensity)

            with tracker.status_lock:
                stimulator.fire()

                # trigger for EEG: 0→1, 1→2, 2→3
                trigger.send(stimulus + 1)

            print("disparando")
            time.sleep(random.uniform(*config.ITI))

            print(f"Index do pulso: {pulse_index + 1}")
            pulse_index += 1

        except Exception as e:
            print(f"\n⚠️ ERRO no pulso {pulse_index}: {e}")
            print("Tentando novamente o mesmo pulso...\n")
            time.sleep(2)

        # ── end condition ─────────────────────────────────────────────
        if pulse_index >= len(sequence):
            print("Encerrando sequência (fim da sequência de pulsos).")
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
    tracker = NavigationTracker(config.NUMBER_OF_RC)
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
    wait_for_key("s", "Aperte a tecla s para iniciar os pulsos...")
    print("start sequence")

    # 6. Run experiment
    try:
        run_experiment(sequence, tracker, stimulator, trigger)
    finally:
        trigger.close()
        tracker.stop()


if __name__ == "__main__":
    main()
