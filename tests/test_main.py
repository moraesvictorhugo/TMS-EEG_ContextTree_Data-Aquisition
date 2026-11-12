"""Test startup selection without connecting or firing physical equipment."""
from unittest.mock import Mock
from threading import Lock

import pytest

from tms_eeg import main as experiment


@pytest.fixture
def startup_mocks(monkeypatch):
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
    monkeypatch.setattr(experiment.config, "TARGET_HISTORY_SIZE", 1)
    monkeypatch.setattr(experiment.keyboard, "is_pressed", lambda key: False)
    monkeypatch.setattr(experiment.time, "sleep", Mock())
    tracker = Mock(all_target_status=True, status_lock=Lock())
    return tracker, Mock(), Mock()


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