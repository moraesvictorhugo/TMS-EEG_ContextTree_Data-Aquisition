"""Pure encoding tests: never instantiate a device or open a serial port."""
import pytest
import magicpy as mp
from unittest.mock import Mock

from tms_eeg import config
from tms_eeg.hardware.magicpy_adapter import MagVenture, PairedPulseMagVenture


def _serial_frame(payload):
    checksum = int(mp.MagVenture.calc_crc([f"{byte:02x}" for byte in payload]), 16)
    return bytes([0xfe, len(payload), *payload, checksum, 0xff])


STATUS = _serial_frame([0, 0x34, 1, 2, 3, 24, 72, 16, 0])
DIDT = bytes.fromhex("fe 04 02 33 19 02 df ff")


def _fake_device(device_class, reply):
    device = object.__new__(device_class)
    device.flush_before_cmd = True
    device.flush_input = Mock()
    device.show_coil_hint = False
    device.sleep_short = 0
    device.port = Mock(is_open=True, in_waiting=len(reply))

    def read(size=1):
        nonlocal reply
        data, reply = reply[:size], reply[size:]
        device.port.in_waiting = len(reply)
        return data

    device.port.read.side_effect = read
    return device


@pytest.mark.parametrize("reply", [DIDT + STATUS, STATUS + DIDT, STATUS])
def test_intensity_sets_mode_with_a_valid_status_reply(monkeypatch, reply):
    monkeypatch.setattr(config, "ENABLE_LOGGING", False)
    monkeypatch.setattr("magicpy.magicpy.time.sleep", Mock())
    device = _fake_device(MagVenture, reply)

    device.set_mode("Standard", "Normal", 2, 10, baratio=80)

    writes = device.port.write.call_args_list
    assert len(writes) == 2
    assert writes[0].args[0][:3] == bytes.fromhex("fe 01 00")
    assert writes[1].args[0][:5] == bytes.fromhex("fe 0b 09 01 01")


@pytest.mark.parametrize("reply", [
    DIDT,
    DIDT + STATUS[:-1],
    DIDT + STATUS + STATUS,
    DIDT + STATUS[:-2] + bytes([STATUS[-2] ^ 1, 0xff]),
    _serial_frame([3, 24, 72, 0]) + STATUS,
])
def test_intensity_rejects_missing_invalid_or_ambiguous_status(monkeypatch, reply):
    monkeypatch.setattr("magicpy.magicpy.time.sleep", Mock())
    device = _fake_device(MagVenture, reply)

    with pytest.raises(ValueError, match="Could not retrieve status"):
        device.set_mode("Standard", "Normal", 2, 10, baratio=80)

    device.port.write.assert_called_once()


@pytest.mark.parametrize("device_class,query", [
    (MagVenture, "get_status"),
    (PairedPulseMagVenture, "get_status_set_get"),
])
def test_status_recovery_does_not_change_other_queries(monkeypatch, device_class, query):
    monkeypatch.setattr("magicpy.magicpy.time.sleep", Mock())
    device = _fake_device(device_class, DIDT + STATUS)

    _, error = getattr(device, query)()

    assert error == 1


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
