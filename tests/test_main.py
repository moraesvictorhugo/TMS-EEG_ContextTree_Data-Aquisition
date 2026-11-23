"""Test startup selection without connecting or firing physical equipment."""
from unittest.mock import Mock
from threading import Lock
from types import SimpleNamespace

import pytest

from tms_eeg import main as experiment


@pytest.fixture
def startup_mocks(monkeypatch):
    monkeypatch.setattr(experiment.config, "NUMBER_OF_BLOCKS", 1)
    monkeypatch.setattr(experiment.config, "MODE", "intensity")
    names = (
        "generate_sequence",
        "generate_pseudo_random_sequence",
        "print_sequence_stats",
        "export_sequence",
        "NavigationTracker",
        "StimulatorController",
        "TriggerSender",
        "wait_for_key",
        "run_experiment",
    )
    mocks = {name: Mock() for name in names}
    mocks["generate_sequence"].return_value = [0, 1, 2]
    mocks["generate_pseudo_random_sequence"].return_value = [0, 1, 2]
    for name, mock in mocks.items():
        monkeypatch.setattr(experiment, name, mock)
    monkeypatch.setattr(experiment.config, "NUMBER_OF_STIMULI", 3)
    monkeypatch.setattr(experiment.config, "ALPHABET", [0, 1, 2])
    monkeypatch.setattr(experiment.config, "VOLUNTEER_CODE", "V00")
    return mocks


@pytest.mark.parametrize(
    "algorithm, selected, unused",
    [
        ("context tree", "generate_sequence", "generate_pseudo_random_sequence"),
        ("pseudo-random", "generate_pseudo_random_sequence", "generate_sequence"),
    ],
)
@pytest.mark.parametrize("export_enabled", [False, True])
def test_startup_selects_generator(
    monkeypatch, capsys, startup_mocks, algorithm, selected, unused, export_enabled
):
    monkeypatch.setattr(experiment.config, "SEQUENCE_ALGORITHM", algorithm)
    monkeypatch.setattr(experiment.config, "EXPORT_SEQUENCE_TXT", export_enabled)
    sequence = [0, 2, 1]
    startup_mocks[selected].return_value = sequence

    experiment.main()

    startup_mocks[selected].assert_called_once_with(3, [0, 1, 2])
    startup_mocks[unused].assert_not_called()
    startup_mocks["print_sequence_stats"].assert_called_once_with(sequence)
    if export_enabled:
        startup_mocks["export_sequence"].assert_called_once_with(
            sequence, 3, "V00", algorithm=algorithm
        )
    else:
        startup_mocks["export_sequence"].assert_not_called()
    startup_mocks["run_experiment"].assert_called_once_with(
        sequence,
        startup_mocks["NavigationTracker"].return_value,
        startup_mocks["StimulatorController"].return_value,
        startup_mocks["TriggerSender"].return_value,
    )
    startup_mocks["NavigationTracker"].return_value.stop.assert_called_once_with()
    startup_mocks["TriggerSender"].return_value.close.assert_called_once_with()
    assert f"Sequence algorithm: {algorithm}" in capsys.readouterr().out


def test_unknown_algorithm_fails_before_hardware(monkeypatch, startup_mocks):
    monkeypatch.setattr(experiment.config, "SEQUENCE_ALGORITHM", "invalid")

    with pytest.raises(ValueError, match="Unknown SEQUENCE_ALGORITHM"):
        experiment.main()

    for mock in startup_mocks.values():
        mock.assert_not_called()


@pytest.mark.parametrize("algorithm", ["context tree", "pseudo-random"])
def test_paired_startup(monkeypatch, startup_mocks, algorithm):
    monkeypatch.setattr(experiment.config, "MODE", "paired-pulse")
    monkeypatch.setattr(experiment.config, "SEQUENCE_ALGORITHM", algorithm)
    monkeypatch.setattr(experiment.config, "EXPORT_SEQUENCE_TXT", False)
    for name in ("generate_sequence", "generate_pseudo_random_sequence"):
        startup_mocks[name].return_value = [0, 1, 2]
    experiment.main()
    startup_mocks["StimulatorController"].assert_called_once_with(
        experiment.config.MAGVENTURE_PORT, paired_pulse=True,
        waveform=experiment.config.PULSE_WAVEFORM,
    )
    startup_mocks["run_experiment"].assert_called_once()


@pytest.mark.parametrize("bad_config", ["mode", "profile", "waveform"])
def test_invalid_protocol_fails_before_connections(monkeypatch, startup_mocks, bad_config):
    monkeypatch.setattr(experiment.config, "MODE", "paired-pulse")
    if bad_config == "mode":
        monkeypatch.setattr(experiment.config, "MODE", "invalid")
    elif bad_config == "profile":
        monkeypatch.setattr(experiment.config, "PULSE_MAP", {})
    else:
        monkeypatch.setattr(experiment.config, "PULSE_WAVEFORM", "BiphasicBurst")
    with pytest.raises(ValueError):
        experiment.main()
    for mock in startup_mocks.values():
        mock.assert_not_called()


def test_actual_tree_output_profiles_validated(monkeypatch, startup_mocks):
    monkeypatch.setattr(experiment.config, "MODE", "paired-pulse")
    monkeypatch.setattr(experiment.config, "SEQUENCE_ALGORITHM", "context tree")
    monkeypatch.setattr(experiment.config, "ALPHABET", [0])
    monkeypatch.setattr(experiment.config, "PULSE_MAP", {0: experiment.config.PULSE_MAP[0]})
    startup_mocks["generate_sequence"].return_value = [0, 1, 2]
    with pytest.raises(ValueError, match="Missing pulse profile"):
        experiment.main()
    startup_mocks["NavigationTracker"].assert_not_called()
    startup_mocks["StimulatorController"].assert_not_called()


@pytest.fixture
def loop_mocks(monkeypatch):
    monkeypatch.setattr(experiment.config, "NUMBER_OF_BLOCKS", 1)
    monkeypatch.setattr(experiment.config, "TARGET_HISTORY_SIZE", 1)
    monkeypatch.setattr(experiment.config, "ITI", (0, 0))
    monkeypatch.setattr(experiment.keyboard, "is_pressed", lambda key: False)
    monkeypatch.setattr(experiment.time, "sleep", Mock())
    tracker = Mock(all_target_status=True, status_lock=Lock())
    return tracker, Mock(), Mock()


@pytest.mark.parametrize("mode,prepare_seconds", [("intensity", 3.5), ("paired-pulse", 3.2)])
def test_iti_includes_preparation_and_restarts_after_overrun(
    monkeypatch, loop_mocks, mode, prepare_seconds
):
    tracker, stimulator, trigger = loop_mocks
    monkeypatch.setattr(experiment.config, "MODE", mode)
    monkeypatch.setattr(experiment.config, "ITI", (4, 6))
    draw = Mock(side_effect=[4, 4.5, 5.75])
    monkeypatch.setattr(experiment.random, "uniform", draw)
    now = 0.0
    fired = []
    starts = []
    durations = iter([prepare_seconds, prepare_seconds, 5, prepare_seconds])

    def sleep(seconds):
        nonlocal now
        now += seconds

    def prepare(_profile):
        starts.append(now)
        sleep(next(durations))

    monkeypatch.setattr(experiment, "time", SimpleNamespace(sleep=sleep, monotonic=lambda: now))
    selected = stimulator.prepare_stimulus if mode == "paired-pulse" else stimulator.prepare_pulse
    selected.side_effect = prepare
    stimulator.fire.side_effect = lambda: fired.append(now)
    experiment.run_experiment([1, 1, 2, 1], tracker, stimulator, trigger)

    assert fired[1] - fired[0] == pytest.approx(4)
    assert fired[2] - fired[1] >= 5
    assert fired[3] - fired[2] == pytest.approx(5.75)
    assert [call.args for call in draw.call_args_list] == [(4, 6)] * 3
    if mode == "paired-pulse":
        assert starts[1] - fired[0] >= experiment.config.PULSE_MAP[1]["ipi_ms"] / 1000
    assert now - fired[-1] < 1


def test_target_loss_while_waiting_for_iti_forces_new_preparation(monkeypatch, loop_mocks):
    tracker, stimulator, trigger = loop_mocks
    monkeypatch.setattr(experiment.config, "MODE", "intensity")
    monkeypatch.setattr(experiment.config, "ITI", (4, 4))
    now = 0.0
    lost_target = False

    def sleep(seconds):
        nonlocal now, lost_target
        now += seconds
        if stimulator.prepare_pulse.call_count == 2 and not lost_target:
            tracker.all_target_status = False
            lost_target = True

    monkeypatch.setattr(experiment, "time", SimpleNamespace(sleep=sleep, monotonic=lambda: now))
    stimulator.disarm.side_effect = lambda: setattr(tracker, "all_target_status", True)
    fired = []
    stimulator.fire.side_effect = lambda: fired.append(now)
    experiment.run_experiment([0, 1], tracker, stimulator, trigger)

    stimulator.disarm.assert_called_once_with()
    assert stimulator.prepare_pulse.call_count == 3
    assert fired == pytest.approx([0, 4])


@pytest.mark.parametrize("mode", ["intensity", "paired-pulse"])
def test_loop_one_fire_and_trigger_per_event(monkeypatch, loop_mocks, mode):
    monkeypatch.setattr(experiment.config, "MODE", mode)
    tracker, stimulator, trigger = loop_mocks
    experiment.run_experiment([0, 1, 2, 0], tracker, stimulator, trigger)
    assert stimulator.fire.call_count == 4
    assert [c.args[0] for c in trigger.send.call_args_list] == [1, 2, 3, 1]
    selected = stimulator.prepare_stimulus if mode == "paired-pulse" else stimulator.prepare_pulse
    unused = stimulator.prepare_pulse if mode == "paired-pulse" else stimulator.prepare_stimulus
    profiles = experiment.config.PULSE_MAP if mode == "paired-pulse" else experiment.config.INTENSITY_MAP
    assert [c.args[0] for c in selected.call_args_list] == [profiles[s] for s in [0, 1, 2, 0]]
    unused.assert_not_called()


def test_loop_preparation_failure_does_not_fire(monkeypatch, loop_mocks):
    monkeypatch.setattr(experiment.config, "MODE", "paired-pulse")
    tracker, stimulator, trigger = loop_mocks
    stimulator.prepare_stimulus.side_effect = RuntimeError("configuration failed")
    # Interrupt at the retry wait to inspect one failed attempt, without looping.
    def stop_on_retry(seconds):
        if seconds == 2:
            raise KeyboardInterrupt
    monkeypatch.setattr(experiment.time, "sleep", stop_on_retry)
    with pytest.raises(KeyboardInterrupt):
        experiment.run_experiment([2], tracker, stimulator, trigger)
    stimulator.fire.assert_not_called()
    trigger.send.assert_not_called()


def test_invalid_pseudo_random_input_fails_before_hardware(monkeypatch, startup_mocks):
    from tms_eeg.sequence import generate_pseudo_random_sequence

    monkeypatch.setattr(experiment.config, "SEQUENCE_ALGORITHM", "pseudo-random")
    monkeypatch.setattr(experiment.config, "ALPHABET", [0])
    monkeypatch.setattr(
        experiment, "generate_pseudo_random_sequence", generate_pseudo_random_sequence
    )

    with pytest.raises(ValueError, match="At least two"):
        experiment.main()

    for mock in startup_mocks.values():
        mock.assert_not_called()


@pytest.mark.parametrize("mode", ["intensity", "paired-pulse"])
def test_preparation_retry_limit(monkeypatch, loop_mocks, mode):
    monkeypatch.setattr(experiment.config, "MODE", mode)
    tracker, stimulator, trigger = loop_mocks
    prepare = stimulator.prepare_pulse if mode == "intensity" else stimulator.prepare_stimulus
    prepare.side_effect = RuntimeError("prepare failed")
    with pytest.raises(RuntimeError, match="prepare failed"):
        experiment.run_experiment([0], tracker, stimulator, trigger)
    assert prepare.call_count == 3
    assert stimulator.disarm.call_count == 3
    stimulator.fire.assert_not_called()


def test_preparation_recovers_after_disarm(monkeypatch, loop_mocks):
    monkeypatch.setattr(experiment.config, "MODE", "intensity")
    tracker, stimulator, trigger = loop_mocks
    stimulator.prepare_pulse.side_effect = [RuntimeError("temporary"), None]
    experiment.run_experiment([0], tracker, stimulator, trigger)
    assert stimulator.prepare_pulse.call_count == 2
    stimulator.disarm.assert_called_once_with()
    stimulator.fire.assert_called_once_with()


def test_preparation_failure_counter_resets_after_success(monkeypatch, loop_mocks):
    monkeypatch.setattr(experiment.config, "MODE", "intensity")
    tracker, stimulator, trigger = loop_mocks
    stimulator.prepare_pulse.side_effect = [
        RuntimeError("temporary"), RuntimeError("temporary"), None,
        RuntimeError("temporary"), RuntimeError("temporary"), None,
    ]
    experiment.run_experiment([0, 1], tracker, stimulator, trigger)
    assert stimulator.fire.call_count == 2
    assert stimulator.disarm.call_count == 4


def test_failed_target_loss_disarm_waits_without_repreparation(monkeypatch, loop_mocks):
    monkeypatch.setattr(experiment.config, "MODE", "intensity")
    tracker, stimulator, trigger = loop_mocks
    stimulator.prepare_pulse.side_effect = lambda value: setattr(tracker, "all_target_status", False)
    stimulator.disarm.side_effect = [RuntimeError("first disarm failed"), None]
    def interrupt_wait(key):
        if key == "r":
            raise KeyboardInterrupt
        return False
    monkeypatch.setattr(experiment.keyboard, "is_pressed", interrupt_wait)
    with pytest.raises(KeyboardInterrupt):
        experiment.run_experiment([0], tracker, stimulator, trigger)
    stimulator.prepare_pulse.assert_called_once()
    stimulator.fire.assert_not_called()
    stimulator.disarm.assert_called_once()


@pytest.mark.parametrize("failure", ["fire", "trigger"])
def test_attempted_fire_never_retried(monkeypatch, loop_mocks, failure):
    monkeypatch.setattr(experiment.config, "MODE", "intensity")
    tracker, stimulator, trigger = loop_mocks
    failing = stimulator.fire if failure == "fire" else trigger.send
    failing.side_effect = RuntimeError("delivery uncertain")
    with pytest.raises(RuntimeError, match="delivery uncertain"):
        experiment.run_experiment([0, 1], tracker, stimulator, trigger)
    stimulator.fire.assert_called_once_with()
    stimulator.prepare_pulse.assert_called_once()
    stimulator.disarm.assert_called_once_with()


def test_disarm_failure_prevents_retry(monkeypatch, loop_mocks):
    monkeypatch.setattr(experiment.config, "MODE", "intensity")
    tracker, stimulator, trigger = loop_mocks
    stimulator.prepare_pulse.side_effect = RuntimeError("prepare")
    stimulator.disarm.side_effect = RuntimeError("disarm")
    with pytest.raises(RuntimeError, match="prepare") as error:
        experiment.run_experiment([0], tracker, stimulator, trigger)
    assert str(error.value.__cause__) == "disarm"
    stimulator.prepare_pulse.assert_called_once()
    stimulator.fire.assert_not_called()


def test_pause_disarms_only_once_and_resume_rechecks_gate(monkeypatch, loop_mocks):
    monkeypatch.setattr(experiment.config, "MODE", "intensity")
    tracker, stimulator, trigger = loop_mocks
    keys = iter([True, False, True, False, False, True])
    monkeypatch.setattr(experiment.keyboard, "is_pressed", lambda key: next(keys))
    experiment.run_experiment([0], tracker, stimulator, trigger)
    stimulator.disarm.assert_called_once_with()
    stimulator.fire.assert_called_once_with()


def test_target_loss_disarms_before_repreparation(monkeypatch, loop_mocks):
    monkeypatch.setattr(experiment.config, "MODE", "intensity")
    tracker, stimulator, trigger = loop_mocks
    def prepare(value):
        if stimulator.prepare_pulse.call_count == 1:
            tracker.all_target_status = False
    stimulator.prepare_pulse.side_effect = prepare
    original_disarm = stimulator.disarm
    original_disarm.side_effect = lambda: setattr(tracker, "all_target_status", True)
    experiment.run_experiment([0], tracker, stimulator, trigger)
    assert stimulator.prepare_pulse.call_count == 2
    stimulator.disarm.assert_called_once_with()
    stimulator.fire.assert_called_once_with()


@pytest.mark.parametrize("mode", ["intensity", "paired-pulse"])
def test_repeated_target_loss_preserves_full_sequence(monkeypatch, loop_mocks, mode):
    monkeypatch.setattr(experiment.config, "MODE", mode)
    monkeypatch.setattr(experiment.config, "TARGET_HISTORY_SIZE", 3)
    tracker, stimulator, trigger = loop_mocks
    sequence = [0, 2, 1, 0]
    original = sequence.copy()
    tracker.all_target_status = False
    waits = 0
    losses = 0
    recovery_at = 8
    prepare = stimulator.prepare_pulse if mode == "intensity" else stimulator.prepare_stimulus
    mapping = experiment.config.INTENSITY_MAP if mode == "intensity" else experiment.config.PULSE_MAP
    fired = []
    def sleep(seconds):
        nonlocal waits
        waits += 1
        assert waits < 200, "Loop failed to recover"
        if not tracker.all_target_status and waits >= recovery_at:
            tracker.all_target_status = True
    def preparation(value):
        nonlocal losses, recovery_at
        if losses < 4:  # More than preparation retry limit, at the same event.
            losses += 1
            tracker.all_target_status = False
            recovery_at = waits + 5
    def fire():
        nonlocal recovery_at
        assert tracker.all_target_status
        fired.append(prepare.call_args.args[0])
        tracker.all_target_status = False  # Also lose target between events.
        recovery_at = waits + 5
    prepare.side_effect = preparation
    stimulator.fire.side_effect = fire
    monkeypatch.setattr(experiment.time, "sleep", sleep)
    experiment.run_experiment(sequence, tracker, stimulator, trigger)
    assert sequence == original
    assert fired == [mapping[s] for s in original]
    assert [c.args[0] for c in trigger.send.call_args_list] == [s + 1 for s in original]
    assert stimulator.disarm.call_count == 4


@pytest.mark.parametrize("mode", ["intensity", "paired-pulse"])
def test_disarm_block_requires_explicit_press_and_preserves_index(monkeypatch, loop_mocks, mode):
    monkeypatch.setattr(experiment.config, "MODE", mode)
    tracker, stimulator, trigger = loop_mocks
    prepare = stimulator.prepare_pulse if mode == "intensity" else stimulator.prepare_stimulus
    # Lose target after event 0 completed, while preparing event 1.
    def preparation(value):
        if prepare.call_count == 2:
            tracker.all_target_status = False
    prepare.side_effect = preparation
    stimulator.disarm.side_effect = [RuntimeError("lost ack"), RuntimeError("lost ack again"), None]
    # G and target recovery do not unblock. Holding R after a failed retry
    # must not flood the serial port: release and press again is required.
    keys = iter([False, True, True, False, True])
    polls = 0
    def pressed(key):
        nonlocal polls
        if key == "r":
            polls += 1
            tracker.all_target_status = True
            assert prepare.call_count == 2
            assert stimulator.fire.call_count == 1
            if polls == 3:
                assert stimulator.disarm.call_count == 2
            return next(keys)
        return key == "g"
    monkeypatch.setattr(experiment.keyboard, "is_pressed", pressed)
    experiment.run_experiment([0, 2, 1], tracker, stimulator, trigger)
    assert polls == 5
    assert stimulator.disarm.call_count == 3
    assert stimulator.fire.call_count == 3
    assert [c.args[0] for c in trigger.send.call_args_list] == [1, 3, 2]
    mapping = experiment.config.INTENSITY_MAP if mode == "intensity" else experiment.config.PULSE_MAP
    assert [c.args[0] for c in prepare.call_args_list] == [mapping[s] for s in [0, 2, 2, 1]]


@pytest.mark.parametrize("stage", ["navigation", "stimulator", "trigger", "wait", "run"])
def test_partial_startup_and_interrupt_cleanup(monkeypatch, startup_mocks, stage):
    monkeypatch.setattr(experiment.config, "SEQUENCE_ALGORITHM", "context tree")
    monkeypatch.setattr(experiment.config, "EXPORT_SEQUENCE_TXT", False)
    calls = {
        "navigation": startup_mocks["NavigationTracker"].return_value.connect,
        "stimulator": startup_mocks["StimulatorController"].return_value.connect,
        "trigger": startup_mocks["TriggerSender"],
        "wait": startup_mocks["wait_for_key"],
        "run": startup_mocks["run_experiment"],
    }
    calls[stage].side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        experiment.main()
    startup_mocks["NavigationTracker"].return_value.stop.assert_called_once_with()
    if stage != "navigation":
        startup_mocks["StimulatorController"].return_value.close.assert_called_once_with()
    if stage in ("wait", "run"):
        startup_mocks["TriggerSender"].return_value.close.assert_called_once_with()


def test_cleanup_failures_preserve_original_error(monkeypatch, startup_mocks):
    monkeypatch.setattr(experiment.config, "SEQUENCE_ALGORITHM", "context tree")
    monkeypatch.setattr(experiment.config, "EXPORT_SEQUENCE_TXT", False)
    startup_mocks["run_experiment"].side_effect = ValueError("original")
    startup_mocks["StimulatorController"].return_value.close.side_effect = RuntimeError("cleanup")
    startup_mocks["TriggerSender"].return_value.close.side_effect = RuntimeError("cleanup")
    with pytest.raises(ValueError, match="original"):
        experiment.main()
    startup_mocks["NavigationTracker"].return_value.stop.assert_called_once_with()


@pytest.mark.parametrize("name, value", [
    ("NUMBER_OF_STIMULI", 0), ("NUMBER_OF_STIMULI", True),
    ("TARGET_HISTORY_SIZE", 0), ("TARGET_HISTORY_SIZE", 1.5),
    ("ITI", (3, 1)), ("ITI", (-1, 2)), ("ITI", (0, float("nan"))),
    ("ITI", (1,)), ("INTENSITY_MAP", {0: 101, 1: 10, 2: 12}),
    ("INTENSITY_MAP", {}),
])
def test_basic_validation_before_connections(monkeypatch, startup_mocks, name, value):
    monkeypatch.setattr(experiment.config, "SEQUENCE_ALGORITHM", "context tree")
    monkeypatch.setattr(experiment.config, name, value)
    with pytest.raises(ValueError):
        experiment.main()
    startup_mocks["NavigationTracker"].assert_not_called()
    startup_mocks["StimulatorController"].assert_not_called()

@pytest.mark.parametrize("mode", ["intensity", "paired-pulse"])
@pytest.mark.parametrize("export_enabled", [False, True])
def test_constant_startup(monkeypatch, startup_mocks, mode, export_enabled):
    monkeypatch.setattr(experiment.config, "MODE", mode)
    monkeypatch.setattr(experiment.config, "SEQUENCE_ALGORITHM", "constant")
    monkeypatch.setattr(experiment.config, "ALPHABET", [2])
    monkeypatch.setattr(experiment.config, "NUMBER_OF_STIMULI", 100)
    monkeypatch.setattr(experiment.config, "EXPORT_SEQUENCE_TXT", export_enabled)
    experiment.main()
    startup_mocks["generate_sequence"].assert_not_called()
    startup_mocks["generate_pseudo_random_sequence"].assert_not_called()
    assert startup_mocks["run_experiment"].call_args.args[0] == [2] * 100
    if export_enabled:
        startup_mocks["export_sequence"].assert_called_once_with(
            [2] * 100, 100, "V00", algorithm="constant")
    else:
        startup_mocks["export_sequence"].assert_not_called()


@pytest.mark.parametrize("alphabet", [[], [0, 1], [2, 2], [True], [15]])
def test_constant_invalid_before_connections(monkeypatch, startup_mocks, alphabet):
    monkeypatch.setattr(experiment.config, "SEQUENCE_ALGORITHM", "constant")
    monkeypatch.setattr(experiment.config, "ALPHABET", alphabet)
    with pytest.raises(ValueError):
        experiment.main()
    startup_mocks["NavigationTracker"].assert_not_called()
    startup_mocks["StimulatorController"].assert_not_called()


@pytest.mark.parametrize("mode", ["intensity", "paired-pulse"])
def test_constant_loop_one_characteristic(monkeypatch, loop_mocks, mode):
    monkeypatch.setattr(experiment.config, "MODE", mode)
    tracker, stimulator, trigger = loop_mocks
    sequence = experiment.generate_constant_sequence(100, [2])
    experiment.run_experiment(sequence, tracker, stimulator, trigger)
    assert stimulator.fire.call_count == 100
    assert [c.args[0] for c in trigger.send.call_args_list] == [3] * 100
    prepare = stimulator.prepare_pulse if mode == "intensity" else stimulator.prepare_stimulus
    mapping = experiment.config.INTENSITY_MAP if mode == "intensity" else experiment.config.PULSE_MAP
    assert [c.args[0] for c in prepare.call_args_list] == [mapping[2]] * 100
