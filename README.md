# TMS-EEG ContextTree Data Acquisition

Experiment controller for TMS-EEG studies using context-tree stimulus sequences.

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
├── sequence.py              ← context-tree sequence generator
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
- `MAGVENTURE_PORT` / `ESP32_SERIAL_PORT` — serial port names

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
