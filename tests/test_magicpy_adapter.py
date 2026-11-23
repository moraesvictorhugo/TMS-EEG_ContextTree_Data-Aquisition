"""Pure encoding tests: never instantiate a device or open a serial port."""
import pytest
import magicpy as mp
from unittest.mock import Mock

from tms_eeg import config
from tms_eeg.hardware.magicpy_adapter import MagVenture, PairedPulseMagVenture


def test_settings_query_with_real_magicpy_decoder(monkeypatch):
    # Synthetic reply for Dual, Normal, Biphasic, IPI index 250 = 2 ms.
    frame = bytes([0xFE, 0x0B, 0x09, 0, 0, 3, 0, 1, 3, 250, 0, 80, 0, 0xFF])
    device = object.__new__(PairedPulseMagVenture)
    device.flush_before_cmd = True
    device.flush_input = Mock()
    device.sleep_short = 0
    device.port = Mock()
    device.port.read.return_value = frame
    device.port.in_waiting = 0
    monkeypatch.setattr("magicpy.magicpy.time.sleep", Mock())

    response, error = device.get_pulse_settings()

    assert error == 0
    assert response["Mode"] == "Dual"
    assert response["CurrentDirection"] == "Normal"
    assert response["Waveform"] == "Biphasic"
    assert response["IPIvalue"] == pytest.approx(2)
    device.flush_input.assert_called_once_with()
    device.port.read.assert_called_once_with(14)
    command = device.port.write.call_args.args[0]
    assert command[:4] == bytes([0xFE, 0x0B, 0x09, 0])
    assert command[4:13] == bytes(9)


def test_raw_status_diagnostics_record_short_reply_without_changing_result(monkeypatch, capsys):
    monkeypatch.setattr(config, "ENABLE_LOGGING", True)
    monkeypatch.setattr("magicpy.magicpy.time.sleep", Mock())
    device = object.__new__(MagVenture)
    device.sleep_short = 0
    device.port = Mock(in_waiting=0)
    read = device.port.read
    read.return_value = b"\xfe\x01\xff"

    assert device.get_status_set_get() == (None, 1)

    assert device.port.read is read
    read.assert_called_once_with(13)
    assert "expected 13 bytes, received 3 bytes (short), result=NoneType, error=1" in capsys.readouterr().out


@pytest.mark.parametrize("ipi", [1, 2.5, 8, 10, 10.1, 25.7, 100, 100.1, 110, 150, 200])
def test_exact_encoding(ipi):
    low, high = PairedPulseMagVenture.parse_ipi(None, ipi)
    assert int(high + low, 16) == round(ipi * 10)


@pytest.mark.parametrize("ticks", range(100, 1001))
def test_legacy_encoding_compatibility(ticks):
    ipi = ticks / 10
    assert PairedPulseMagVenture.parse_ipi(None, ipi) == mp.MagVenture.parse_ipi(None, ipi)


@pytest.mark.parametrize("ipi", [None, True, False, "2.5", -1, 0, 0.5, 200.1,
                                      float("nan"), float("inf"), 2.55])
def test_invalid_ipi(ipi):
    with pytest.raises(ValueError):
        PairedPulseMagVenture.parse_ipi(None, ipi)


def test_original_library_is_not_patched():
    with pytest.raises(ValueError):
        mp.MagVenture.parse_ipi(None, 2.5)
    with pytest.raises(ValueError):
        mp.MagVenture.parse_ipi(None, 200)


@pytest.mark.parametrize("ipi, index", [(100, 70), (110, 69), (150, 65), (200, 60)])
def test_real_magicpy_dual_response_decoding(ipi, index):
    # Synthetic Get Response frame (command 09), not a device measurement.
    # Reply IPIs are device indices, distinct from outgoing tenths-of-ms values.
    frame = bytes([0xFE, 0x0B, 0x09, 0, 0, 3, 0, 1, 3,
                   index, 0, 80, 0, 0xFF])
    device = object.__new__(PairedPulseMagVenture)
    response, raw = device.parse_response(frame)
    assert response["Mode"] == "Dual"
    assert response["IPIvalue"] == ipi
    low, high = device.parse_ipi(ipi)
    assert raw["IPIValue_LSB"] == low
    assert raw["IPIValue_MSB"] == high
