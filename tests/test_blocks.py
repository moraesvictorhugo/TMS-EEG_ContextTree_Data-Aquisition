"""Block boundaries preserve the full algorithmic sequence; no device access."""
from threading import Lock
from unittest.mock import Mock

import pytest

from tms_eeg import main as experiment


@pytest.mark.parametrize("constant", [False, True])
@pytest.mark.parametrize("mode", ["intensity", "paired-pulse"])
@pytest.mark.parametrize("total, blocks", [(4, 1), (400, 2), (12, 3), (4, 4)])
def test_block_pauses_preserve_sequence(monkeypatch, mode, total, blocks, constant):
    monkeypatch.setattr(experiment.config, "MODE", mode)
    monkeypatch.setattr(experiment.config, "NUMBER_OF_BLOCKS", blocks)
    monkeypatch.setattr(experiment.config, "TARGET_HISTORY_SIZE", 3)
    tracker = Mock(all_target_status=True, status_lock=Lock())
    stimulator, trigger = Mock(), Mock()
    sequence = (experiment.generate_constant_sequence(total, [2]) if constant
                else [i % 3 for i in range(total)])
    original = sequence.copy()
    boundary_polls = {}
    def key(key):
        if key != "g":
            return False
        completed = stimulator.fire.call_count
        if completed and completed < total and completed % (total // blocks) == 0:
            boundary_polls[completed] = boundary_polls.get(completed, 0) + 1
            # Require several paused polls, including release of G.
            assert stimulator.prepare_pulse.call_count + stimulator.prepare_stimulus.call_count == completed
            return boundary_polls[completed] >= 4
        return False
    monkeypatch.setattr(experiment.keyboard, "is_pressed", key)
    monkeypatch.setattr(experiment.time, "sleep", Mock())
    experiment.run_experiment(sequence, tracker, stimulator, trigger)
    assert sequence == original
    assert stimulator.disarm.call_count == blocks - 1
    assert len(boundary_polls) == blocks - 1
    assert [c.args[0] for c in trigger.send.call_args_list] == [s + 1 for s in original]
    mapping = experiment.config.INTENSITY_MAP if mode == "intensity" else experiment.config.PULSE_MAP
    prepare = stimulator.prepare_pulse if mode == "intensity" else stimulator.prepare_stimulus
    assert [c.args[0] for c in prepare.call_args_list] == [mapping[s] for s in original]


def test_block_disarm_recovery_still_requires_g(monkeypatch):
    monkeypatch.setattr(experiment.config, "MODE", "intensity")
    monkeypatch.setattr(experiment.config, "NUMBER_OF_BLOCKS", 2)
    monkeypatch.setattr(experiment.config, "TARGET_HISTORY_SIZE", 1)
    tracker = Mock(all_target_status=True, status_lock=Lock())
    stimulator, trigger = Mock(), Mock()
    stimulator.disarm.side_effect = [RuntimeError("ack missing"), None]
    g_polls = 0
    def key(key):
        nonlocal g_polls
        if key == "r":
            assert stimulator.fire.call_count == 2
            return True
        if key == "g" and stimulator.fire.call_count == 2:
            assert stimulator.disarm.call_count == 2
            assert stimulator.prepare_pulse.call_count == 2
            g_polls += 1
            return g_polls >= 3
        return False
    monkeypatch.setattr(experiment.keyboard, "is_pressed", key)
    monkeypatch.setattr(experiment.time, "sleep", Mock())
    experiment.run_experiment([0, 1, 2, 0], tracker, stimulator, trigger)
    assert g_polls == 3
    assert [c.args[0] for c in trigger.send.call_args_list] == [1, 2, 3, 1]


@pytest.mark.parametrize("blocks", [0, -1, True, 1.5, 5, 3])
def test_invalid_blocks_rejected_before_connections(monkeypatch, blocks):
    monkeypatch.setattr(experiment.config, "NUMBER_OF_STIMULI", 4)
    monkeypatch.setattr(experiment.config, "NUMBER_OF_BLOCKS", blocks)
    navigation, stimulator = Mock(), Mock()
    monkeypatch.setattr(experiment, "NavigationTracker", navigation)
    monkeypatch.setattr(experiment, "StimulatorController", stimulator)
    with pytest.raises(ValueError):
        experiment.main()
    navigation.assert_not_called()
    stimulator.assert_not_called()