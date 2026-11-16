"""Controller and profile tests using mocks only; no equipment access."""
from copy import deepcopy
from unittest.mock import Mock, call

import pytest

from tms_eeg import config
from tms_eeg.hardware import stimulator as module


@pytest.fixture
def controller(monkeypatch):
    monkeypatch.setattr(module.time, "sleep", Mock())
    controller = module.StimulatorController("unused", paired_pulse=True)
    device = Mock()
    controller._stimulator = device
    for name in ("set_mode", "arm", "set_amplitude"):
        getattr(device, name).return_value = ({}, 0)
    device.set_waveform.return_value = (
        {"Mode": "Dual", "Waveform": "Biphasic", "CurrentDirection": "Normal"}, 0
    )
    device.get_mode.return_value = ("Dual", 0)
    device.get_ipi.return_value = (config.PULSE_MAP[2]["ipi_ms"], 0)
    return controller


def test_paired_preparation_and_single_fire(controller):
    profile = config.PULSE_MAP[2]
    controller.prepare_stimulus(profile)
    device = controller._stimulator
    device.set_mode.assert_called_once_with(
        mode="Dual", current_dir="Normal", n_pulses_per_burst=2,
        ipi=profile["ipi_ms"], baratio=1, get_response=True,
    )
    device.set_amplitude.assert_called_once_with(
        profile["a_intensity"], b_amp=profile["b_intensity"], get_response=True
    )
    controller.fire()
    device.fire.assert_called_once_with()
    with pytest.raises(RuntimeError, match="prepared"):
        controller.fire()


def test_single_paired_single_transition(controller):
    device = controller._stimulator
    for symbol in [0, 1, 0]:
        profile = config.PULSE_MAP[symbol]
        mode = "Standard" if symbol == 0 else "Dual"
        device.set_waveform.return_value = (
            {"Mode": mode, "Waveform": "Biphasic", "CurrentDirection": "Normal"}, 0
        )
        device.get_mode.return_value = (mode, 0)
        device.get_ipi.return_value = (profile.get("ipi_ms", 10), 0)
        controller.prepare_stimulus(profile)
        controller.fire()
    assert [c.kwargs["mode"] for c in device.set_mode.call_args_list] == [
        "Standard", "Dual", "Standard"
    ]
    assert [c.kwargs["b_amp"] for c in device.set_amplitude.call_args_list] == [
        None, config.PULSE_MAP[1]["b_intensity"], None
    ]
    assert device.fire.call_count == 3


@pytest.mark.parametrize("operation", ["set_mode", "set_waveform", "arm",
                                        "set_amplitude", "get_mode", "get_ipi"])
def test_error_blocks_firing(controller, operation):
    getattr(controller._stimulator, operation).return_value = ("Empty", 1)
    with pytest.raises(RuntimeError):
        controller.prepare_stimulus(config.PULSE_MAP[2])
    with pytest.raises(RuntimeError, match="prepared"):
        controller.fire()
    controller._stimulator.fire.assert_not_called()


@pytest.mark.parametrize("operation, response", [
    ("get_mode", "Standard"), ("get_ipi", 8),
    ("set_waveform", {"Mode": "Dual", "Waveform": "BiphasicBurst"}),
])
def test_readback_mismatch_blocks_firing(controller, operation, response):
    getattr(controller._stimulator, operation).return_value = (response, 0)
    with pytest.raises(RuntimeError, match="mismatch"):
        controller.prepare_stimulus(config.PULSE_MAP[2])
    with pytest.raises(RuntimeError):
        controller.fire()


def test_failed_repreparation_invalidates_previous_event(controller):
    controller.prepare_stimulus(config.PULSE_MAP[2])
    with pytest.raises(ValueError):
        controller.prepare_stimulus({})
    with pytest.raises(RuntimeError):
        controller.fire()


def test_legacy_preparation_unchanged(monkeypatch):
    monkeypatch.setattr(module.time, "sleep", Mock())
    controller = module.StimulatorController("unused")
    device = Mock()
    controller._stimulator = device
    controller.prepare_pulse(12)
    controller.fire()
    assert device.mock_calls == [
        call.set_mode(mode="Standard", current_dir="Normal", n_pulses_per_burst=2,
                      ipi=10, baratio=80),
        call.arm(get_response=False), call.set_amplitude(12, b_amp=None), call.fire(),
    ]


@pytest.mark.parametrize("paired", [False, True])
def test_connection_selects_opt_in_class(monkeypatch, paired):
    original, adapter = Mock(), Mock()
    monkeypatch.setattr(module.mp, "MagVenture", original)
    monkeypatch.setattr(module, "PairedPulseMagVenture", adapter)
    monkeypatch.setattr(module.mp, "list_serial_ports", Mock())
    monkeypatch.setattr("builtins.input", Mock())
    module.StimulatorController("unused", paired_pulse=paired).connect()
    selected, other = (adapter, original) if paired else (original, adapter)
    selected.assert_called_once_with("unused")
    other.assert_not_called()


@pytest.mark.parametrize("field, value", [
    ("a_intensity", -1), ("a_intensity", 101), ("a_intensity", True),
    ("b_intensity", 12.5), ("b_intensity", None), ("ipi_ms", 2.55),
    ("type", "unknown"), ("label", ""),
])
def test_invalid_profile(field, value):
    profile = deepcopy(config.PULSE_MAP[2])
    profile[field] = value
    with pytest.raises(ValueError):
        module.validate_profile(profile)


def test_protocol_validation():
    module.validate_protocol("paired-pulse", [0, 1, 2], config.PULSE_MAP, "Biphasic")
    module.validate_protocol("intensity", [], None, "invalid")
    for mode, alphabet, profiles, waveform in [
        ("invalid", [0], config.PULSE_MAP, "Biphasic"),
        ("paired-pulse", [3], config.PULSE_MAP, "Biphasic"),
        ("paired-pulse", [15], config.PULSE_MAP, "Biphasic"),
        ("paired-pulse", [0], config.PULSE_MAP, "BiphasicBurst"),
        ("paired-pulse", [], config.PULSE_MAP, "Biphasic"),
    ]:
        with pytest.raises(ValueError):
            module.validate_protocol(mode, alphabet, profiles, waveform)


def test_single_rejects_paired_fields():
    profile = dict(config.PULSE_MAP[0], b_intensity=None)
    with pytest.raises(ValueError):
        module.validate_profile(profile)


@pytest.mark.parametrize("label, ipi", [("SICI", 2.5), ("LICI", 150), ("LICI", 200)])
def test_arbitrary_paired_labels_and_extended_ipi(controller, label, ipi):
    profile = dict(config.PULSE_MAP[2], label=label, ipi_ms=ipi)
    profiles = {
        1: dict(config.PULSE_MAP[1], label="SICI"),
        2: profile,
    }
    module.validate_protocol("paired-pulse", [1, 2], profiles, "Biphasic")
    controller._stimulator.get_ipi.return_value = (ipi, 0)
    controller.prepare_stimulus(profile)
    assert controller._stimulator.set_mode.call_args.kwargs["ipi"] == ipi
    controller.fire()
    controller._stimulator.fire.assert_called_once_with()


def test_extended_ipi_readback_is_not_silently_rounded(controller):
    profile = dict(config.PULSE_MAP[2], label="LICI", ipi_ms=150.1)
    controller._stimulator.get_ipi.return_value = (150, 0)
    with pytest.raises(RuntimeError, match="readback mismatch"):
        controller.prepare_stimulus(profile)
    with pytest.raises(RuntimeError, match="prepared"):
        controller.fire()
    controller._stimulator.fire.assert_not_called()


def test_disarm_invalidates_preparation(controller):
    controller.prepare_stimulus(config.PULSE_MAP[2])
    controller._stimulator.disarm.return_value = ({}, 0)
    controller.disarm()
    controller._stimulator.disarm.assert_called_once_with(get_response=True)
    with pytest.raises(RuntimeError, match="prepared"):
        controller.fire()


def test_close_disconnects_even_after_failed_disarm(controller, monkeypatch, capsys):
    monkeypatch.setattr(config, "ENABLE_LOGGING", False)
    controller._prepared = True
    controller._stimulator.disarm.return_value = ("Empty", 1)
    controller.close()
    assert not controller._prepared
    controller._stimulator.disconnect.assert_called_once_with()
    assert "NOT confirmed" in capsys.readouterr().out


def test_close_before_connection():
    module.StimulatorController("unused").close()


@pytest.mark.parametrize("reply", ["Empty", [
    {"Status": "Disabled", "amplitudePercentage_A": 10},
    {"Status": "Disabled", "Temperature": 24},
]])
def test_disarm_error_recovers_only_with_fresh_disabled_status(controller, reply):
    controller._prepared = True
    device = controller._stimulator
    device.disarm.return_value = (reply, 1)
    device.get_status.return_value = ({"Status": "Disabled"}, 0)

    controller.disarm()

    assert not controller._prepared
    assert device.mock_calls == [call.disarm(get_response=True), call.get_status()]
    with pytest.raises(RuntimeError, match="prepared"):
        controller.fire()
    device.fire.assert_not_called()


@pytest.mark.parametrize("readback", [
    ({"Status": "Enabled"}, 0),
    ({"Status": "Disabled"}, 1),
    ("Empty", 1),
    ({}, 0),
    ([{"Status": "Disabled"}], 0),
])
def test_disarm_error_remains_blocked_without_valid_readback(controller, readback):
    controller._prepared = True
    device = controller._stimulator
    device.disarm.return_value = ([{"Status": "Disabled"}], 1)
    device.get_status.return_value = readback

    with pytest.raises(RuntimeError, match="independent status check failed"):
        controller.disarm()

    assert not controller._prepared
    device.fire.assert_not_called()


def test_acknowledged_disarm_needs_no_fallback(controller):
    controller._stimulator.disarm.return_value = ({"Status": "Disabled"}, 0)
    controller.disarm()
    controller._stimulator.get_status.assert_not_called()
