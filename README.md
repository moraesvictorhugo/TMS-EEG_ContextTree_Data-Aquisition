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
