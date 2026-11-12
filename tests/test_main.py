"""Test startup selection without connecting or firing physical equipment."""
from unittest.mock import Mock

import pytest

from tms_eeg import main as experiment


@pytest.fixture
def startup_mocks(monkeypatch):
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