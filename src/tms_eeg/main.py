"""
TMS-EEG ContextTree Data Acquisition — experiment entry point.

This script orchestrates the full experiment:
  1. Generate a stimulus sequence using the configured algorithm
  2. Connect to neuronavigation, stimulator, and trigger board
  3. Run the experiment loop with pause/resume support
"""
import random
import time
import traceback
import math
from numbers import Real
from collections import deque
import keyboard
from tms_eeg import config
from tms_eeg.sequence import (
    generate_sequence,
    generate_pseudo_random_sequence,
    generate_constant_sequence,
    print_sequence_stats,
    export_sequence,
)
from tms_eeg.hardware.stimulator import StimulatorController, validate_protocol
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


def trials_per_block(total):
    """Return equal block size; reject implicit rounding or empty blocks."""
    blocks = config.NUMBER_OF_BLOCKS
    if type(blocks) is not int or blocks <= 0:
        raise ValueError("NUMBER_OF_BLOCKS must be a positive integer.")
    if blocks > total or total % blocks:
        raise ValueError("Trials must be divisible by NUMBER_OF_BLOCKS, with at least one trial per block.")
    return total // blocks


def validate_settings(sequence=None):
    """Check basic acquisition settings before opening any connections."""
    for name in ("NUMBER_OF_STIMULI", "TARGET_HISTORY_SIZE"):
        value = getattr(config, name)
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer.")
    trials_per_block(config.NUMBER_OF_STIMULI)
    if not isinstance(config.ITI, (tuple, list)) or len(config.ITI) != 2:
        raise ValueError("ITI must contain two finite, non-negative values.")
    if any(isinstance(v, bool) or not isinstance(v, Real) or
           not math.isfinite(v) or v < 0 for v in config.ITI) or config.ITI[0] > config.ITI[1]:
        raise ValueError("ITI must be finite, non-negative and ordered.")
    if sequence is None:
        return
    trials_per_block(len(sequence))
    for symbol in sequence:
        if type(symbol) is not int or not 0 <= symbol <= 14:
            raise ValueError("Sequence symbols must be integers 0–14 (EEG codes 1–15).")
        if config.MODE == "intensity":
            intensity = config.INTENSITY_MAP.get(symbol)
            if type(intensity) is not int or not 0 <= intensity <= 100:
                raise ValueError(f"Invalid or missing intensity for symbol {symbol}.")


def cleanup(stimulator, trigger, tracker):
    """Release partially initialized resources without masking the primary error."""
    for resource, method in ((stimulator, "close"), (trigger, "close"), (tracker, "stop")):
        if resource is not None:
            try:
                getattr(resource, method)()
            except Exception as error:
                print(f"WARNING: cleanup {method} failed: {error}")


def run_experiment(sequence, tracker, stimulator, trigger):
    """Execute the main experiment loop.

    Fires TMS pulses according to *sequence*, gated by neuronavigation
    target tracking. Supports manual/block pause and resume (G key).

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
    preparation_failures = 0
    disarm_blocked = False
    retry_key_was_pressed = False
    block_size = trials_per_block(len(sequence))
    last_block_boundary = 0
    block_pause = False
    block_resume_released = False

    while True:
        # ── safety bounds check ───────────────────────────────────────
        if pulse_index >= len(sequence):
            log(f"Safety bounds check: pulse_index ({pulse_index}) >= sequence length ({len(sequence)}). Breaking loop.", "DEBUG")
            break

        # Handle each internal boundary once, outside the previous event's
        # error handler. Never regenerate/slice the sequence or reset its index.
        if pulse_index and pulse_index % block_size == 0 and pulse_index != last_block_boundary:
            last_block_boundary = pulse_index
            paused = True
            block_pause = True
            block_resume_released = False
            target_history.clear()
            target_history.extend([False] * config.TARGET_HISTORY_SIZE)
            print(f"Block {pulse_index // block_size}/{config.NUMBER_OF_BLOCKS} complete "
                  f"({pulse_index}/{len(sequence)} trials). Press G to start the next block.")
            try:
                stimulator.disarm()
            except Exception as error:
                disarm_blocked = True
                retry_key_was_pressed = False
                print(f"Disarm NOT confirmed at block boundary: {error}. "
                      "Firing blocked; check device and press R to retry, then G to resume.")

        # A target-loss/block disarm failure preserves this event in memory. Only
        # an explicit R press may retry disarm; G/target recovery cannot bypass it.
        if disarm_blocked:
            retry_pressed = keyboard.is_pressed("r")
            if retry_pressed and not retry_key_was_pressed:
                try:
                    stimulator.disarm()
                except Exception as error:
                    print(f"Disarm still unconfirmed: {error}. Press R again to retry; no firing allowed.")
                else:
                    disarm_blocked = False
                    target_history.clear()
                    target_history.extend([False] * config.TARGET_HISTORY_SIZE)
                    if block_pause:
                        print("Disarm confirmed. Block pause remains active; press G to resume.")
                    else:
                        print(f"Disarm confirmed. Waiting for target at event {pulse_index + 1}.")
            retry_key_was_pressed = retry_pressed
            time.sleep(0.05)
            continue

        # ── pause / resume ────────────────────────────────────────────
        if keyboard.is_pressed("b") and not paused:
            stimulator.disarm()
            paused = True
            log("Paused sequence (key B).", "INFO")
            print("Paused sequence (key B).")
        resume_pressed = keyboard.is_pressed("g")
        if block_pause and not resume_pressed:
            block_resume_released = True
        if resume_pressed and paused and (not block_pause or block_resume_released):
            paused = False
            block_pause = False
            target_history.clear()
            target_history.extend([False] * config.TARGET_HISTORY_SIZE)
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
        fire_attempted = False
        stage = "preparation"
        stimulus = sequence[pulse_index]
        try:
            if config.MODE == "paired-pulse":
                profile = config.PULSE_MAP[stimulus]
                print(f"Pulse profile: {profile} (event {stimulus})")
                stimulator.prepare_stimulus(profile)
            else:
                intensity = config.INTENSITY_MAP[stimulus]
                log(f"Sequence requested stimulus: {stimulus}, Intensity mapping: {intensity}", "DEBUG")
                print(f"Intensity: {intensity} (event {stimulus})")

                log("Calling stimulator.prepare_pulse()", "DEBUG")
                stimulator.prepare_pulse(intensity)
            log("Stimulator armed successfully.", "DEBUG")

            with tracker.status_lock:
                target_lost = not tracker.all_target_status
                if not target_lost:
                    log("Calling stimulator.fire()", "DEBUG")
                    stage = "fire (delivery uncertain on failure)"
                    fire_attempted = True
                    stimulator.fire()
                    # trigger for EEG: 0→1, 1→2, 2→3
                    log(f"Sending trigger value: {stimulus + 1}", "DEBUG")
                    stage = "EEG trigger after fire"
                    trigger.send(stimulus + 1)

            if target_lost:
                # Normal operational wait, not a failed preparation. Release
                # the navigation lock before serial I/O so tracking can update.
                print(f"Coil out of target. Waiting at event {pulse_index + 1}; sequence preserved.")
                target_history.clear()
                target_history.extend([False] * config.TARGET_HISTORY_SIZE)
                try:
                    stimulator.disarm()
                except Exception as error:
                    disarm_blocked = True
                    retry_key_was_pressed = False
                    print(f"Disarm NOT confirmed: {error}. Event {pulse_index + 1} preserved; "
                          "firing blocked. Check device, then press R to retry disarm (Ctrl+C to exit).")
                continue

            print("Firing")
            time.sleep(random.uniform(*config.ITI))

            print(f"Pulse index: {pulse_index + 1}")
            log(f"Pulse index {pulse_index} successfully fired.", "INFO")
            pulse_index += 1
            preparation_failures = 0

        except Exception as e:
            error_details = traceback.format_exc()
            log(f"Exception during pulse firing:\n{error_details}", "ERROR")
            print(f"\n⚠️ ERRO in pulse {pulse_index}: {e}")
            print(f"Event index={pulse_index}, symbol={stimulus}, stage={stage}.")
            # An attempted fire may already have delivered a pulse, even if it raised.
            # Disarm must succeed before considering any preparation retry.
            if fire_attempted:
                print("STOP: delivery/marking uncertain. Event will NOT be repeated.")
            try:
                stimulator.disarm()
            except Exception as disarm_error:
                print(f"STOP: disarm not confirmed: {disarm_error}. No retry allowed.")
                raise e from disarm_error
            if fire_attempted:
                raise
            preparation_failures += 1
            if preparation_failures >= 3:
                print("STOP: three preparation failures for this event.")
                raise
            print(f"Retrying preparation ({preparation_failures + 1}/3) after confirmed disarm.")
            time.sleep(2)

        # ── end condition ─────────────────────────────────────────────
        if pulse_index >= len(sequence):
            print("Ending sequence (end of pulse sequence).")
            break

        time.sleep(0.01)


def main():
    """Set up all subsystems and run the experiment."""

    validate_protocol(config.MODE, config.ALPHABET, config.PULSE_MAP, config.PULSE_WAVEFORM)
    validate_settings()

    # 1. Sequence generation
    if config.SEQUENCE_ALGORITHM == "context tree":
        sequence = generate_sequence(config.NUMBER_OF_STIMULI, config.ALPHABET)
    elif config.SEQUENCE_ALGORITHM == "pseudo-random":
        sequence = generate_pseudo_random_sequence(
            config.NUMBER_OF_STIMULI, config.ALPHABET
        )
    elif config.SEQUENCE_ALGORITHM == "constant":
        sequence = generate_constant_sequence(config.NUMBER_OF_STIMULI, config.ALPHABET)
    else:
        raise ValueError(
            f"Unknown SEQUENCE_ALGORITHM: {config.SEQUENCE_ALGORITHM!r}. "
            "Expected 'context tree', 'pseudo-random' or 'constant'."
        )
    print(f"Sequence algorithm: {config.SEQUENCE_ALGORITHM}")
    validate_settings(sequence)
    print_sequence_stats(sequence)
    if config.MODE == "paired-pulse":
        # Validate actual output too: context-tree transitions can emit 0/1/2
        # even if the supplied alphabet only restricted its initial symbol.
        validate_protocol(config.MODE, sorted(set(sequence)), config.PULSE_MAP,
                          config.PULSE_WAVEFORM)
        print(f"Requested pulse profiles (% MSO, IPI in ms): {config.PULSE_MAP}")

    if config.EXPORT_SEQUENCE_TXT:
        export_sequence(
            sequence,
            config.NUMBER_OF_STIMULI,
            config.VOLUNTEER_CODE,
            algorithm=config.SEQUENCE_ALGORITHM,
        )

    tracker = stimulator = trigger = None
    try:
        # Include partial startup and the operator wait in the cleanup scope.
        tracker = NavigationTracker()
        tracker.connect(config.NAVIGATION_ADDRESS, config.NAVIGATION_PORTS)
        if config.MODE == "paired-pulse":
            stimulator = StimulatorController(
                config.MAGVENTURE_PORT, paired_pulse=True, waveform=config.PULSE_WAVEFORM
            )
        else:
            stimulator = StimulatorController(config.MAGVENTURE_PORT)
        stimulator.connect()
        trigger = TriggerSender(
            config.ESP32_SERIAL_PORT,
            config.ESP32_BAUD_RATE,
            config.ESP32_STARTUP_DELAY,
        )
        wait_for_key("s", "Press the 's' key to start the pulses....")
        print("start sequence")
        run_experiment(sequence, tracker, stimulator, trigger)
    finally:
        cleanup(stimulator, trigger, tracker)


if __name__ == "__main__":
    main()
