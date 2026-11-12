# TMS-EEG ContextTree Data Acquisition

Experiment controller for TMS-EEG studies using context-tree or pseudo-random stimulus sequences.

Controls a **MagVenture** TMS stimulator at varying intensities (80 / 100 / 120 % rMT),
monitors coil position through **InVesalius** neuronavigation, and sends 4-bit binary
triggers to an **ESP32** microcontroller for EEG event marking.

## Quick start

```bash
# Install uv (if you haven't)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run the experiment
uv run tms-eeg
```

## Project structure

```
src/tms_eeg/
├── main.py                  ← experiment entry point
├── config.py                ← all experiment settings (edit before each session)
├── sequence.py              ← context-tree and pseudo-random sequence generators
├── hardware/
│   ├── stimulator.py        ← MagVenture controller
│   └── trigger.py           ← ESP32 serial trigger sender
└── navigation/
    ├── remote_control.py    ← Socket.IO relay client
    └── tracker.py           ← coil-on-target tracker

firmware/
└── trigger.ino              ← ESP32 Arduino firmware

tests/
└── test_sequence.py         ← sequence generation tests
```

## Configuration

Edit `src/tms_eeg/config.py` before each experiment session:
- `VOLUNTEER_CODE` — volunteer identifier
- `RMT_INTENSITY` — resting motor threshold (% MSO)
- `NUMBER_OF_STIMULI` — total number of trials
- `SEQUENCE_ALGORITHM` — `"context tree"` (default) or `"pseudo-random"`
- `MAGVENTURE_PORT` / `ESP32_SERIAL_PORT` — serial port names

### Sequence generation

In the existing **Sequence generation** section of the config, select:

```python
SEQUENCE_ALGORITHM = "pseudo-random"  # or "context tree" for the original behavior
```

Pseudo-random generation chooses the first symbol uniformly from `ALPHABET`,
then chooses uniformly among all symbols other than the previous one. For example,
`0, 2, 0, 1, 2, 1` is valid. Counts per stimulus type are **not guaranteed to be equal**.
The alphabet must be nonempty and contain distinct symbols; more than one trial
requires at least two symbols. Keep symbols mapped in `INTENSITY_MAP` (normally
`[0, 1, 2]`). An unknown algorithm is rejected before connecting equipment.

Intensity mapping, EEG triggers, timing, pause/resume and target tracking are
unchanged. The no-repeat rule applies to the generated symbols, not hardware
retries: the existing error handler can retry the same pulse after an exception.
Different symbols imply different intensities only when their mapped values differ.

With `EXPORT_SEQUENCE_TXT = True`, context-tree filenames retain the existing
`tree_sequence_...` prefix; pseudo-random filenames use `pseudo_random_sequence_...`.

## Simple and paired-pulse protocol

The default `MODE = "intensity"` retains the original intensity mapping and
preparation. To opt in, edit the existing config:

```python
MODE = "paired-pulse"
PULSE_WAVEFORM = "Biphasic"
```

Configure `PULSE_MAP` before enabling this protocol:

| Symbol / EEG code | Condition | Required fields |
|---|---|---|
| `0` / `1` | Simple | `type="single"`, `label`, `a_intensity` |
| `1` / `2` | `paired_1` | `type="paired"`, `label`, `a_intensity`, `b_intensity`, `ipi_ms` |
| `2` / `3` | `paired_2` | `type="paired"`, `label`, `a_intensity`, `b_intensity`, `ipi_ms` |

The shipped profiles are **examples, not a validated experimental prescription**.
Set A (conditioning) and B (test) independently for each pair in integer **% MSO**
(`0–100`), and set each condition's onset-to-onset IPI in **milliseconds**.
The example IPIs remain `8.0` and `2.5` ms. Labels are arbitrary and do not control
stimulation: both profiles may be inhibitory conditions, such as SICI and LICI.
Rename `label` and configure each profile's A/B intensities and IPI explicitly;
choosing a label never automatically selects parameters or guarantees an effect.

`SEQUENCE_ALGORITHM` still selects order independently. `NUMBER_OF_STIMULI` counts
**events/trials**, not physical pulses: each paired event contains two pulses.
Pseudo-random excludes the previous condition, not pulses inside a pair.

The paired protocol uses Standard for singles and Dual for pairs, explicit
non-burst waveform (`Monophasic`, `Biphasic` or `HalfSine`), Normal direction and
B/A ratio `1`. Burst index configuration remains `2` as required by MagicPy;
it is not used to synthesize the pair. Each event is configured anew, including
paired-to-single transitions. A single `fire()` requests the hardware-timed pair;
Python never schedules separate A/B fire commands. Preparation checks command
responses, mode/waveform/direction readback and final mode/IPI. Missing or
mismatched readback blocks firing rather than silently proceeding. Communication
success does not independently measure the actual amplitudes or physical pulses.

The local `PairedPulseMagVenture` subclass encodes explicit `1–200 ms` IPIs in
`0.1 ms` increments, reproducing the reference project's lower-bound patch
without modifying `.venv` or globally patching MagicPy. It rejects missing,
nonfinite or nonrepresentable IPIs instead of silently truncating. MagicPy is
pinned to `0.1.6`; the adapter is used **only** for this protocol.

Encoding resolution is not device resolution: MagicPy's Dual/Twin response
decoder represents `100–200 ms` in `10 ms` steps (e.g. `110`, `150`, `200`).
An encodable value such as `150.1 ms` is not guaranteed to be physically supported.
No silent rounding is performed: if device readback differs from the requested
IPI, preparation fails and firing is blocked. Validate long intervals in the lab.

**Before experimental use**, confirm model/firmware Dual support and waveform
compatibility, inspect device readback, and measure pulse count, A/B amplitudes,
IPI and paired-to-single transitions in the lab. The software's accepted interval
is not proof of the equipment's capabilities. Do not change the non-burst
waveform to `BiphasicBurst` to try to obtain pairs.

The ESP32 firmware is unchanged: one EEG code marks the condition/event, not
individually synchronized A/B onsets. Existing software-trigger jitter and retry
behavior remain: an exception after firing can cause an event to be attempted
again. Requested profiles are printed at startup and per event; use actual device
records/measurements to confirm delivery. Preparation adds response/readback time
in addition to the original waits; ITI remains the post-event wait, not a precise
onset-to-onset trial interval.

## Testing

See [TESTING.md](TESTING.md) for details.

```bash
uv run pytest
```

## Keyboard controls during experiment

| Key | Action |
|-----|--------|
| `S` | Start the pulse sequence |
| `B` | Pause the sequence |
| `G` | Resume the sequence |
