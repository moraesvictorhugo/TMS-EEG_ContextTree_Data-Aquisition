# Testing Guide

This project uses [pytest](https://docs.pytest.org/) to run automated tests and [uv](https://docs.astral.sh/uv/) to manage the environment.

## What is tested?

The tests cover both sequence generators, text export and startup algorithm
selection. Startup tests mock all hardware, keyboard interaction and experiment
execution, so they do not connect equipment or fire pulses. They check:

| Test | What it verifies |
|---|---|
| Symbol transitions | After `2` → always `1`; after `(1,1)` → `0`; etc. |
| Sequence length | Output has exactly the requested number of stimuli |
| Valid symbols | Every element is `0`, `1`, or `2` |
| Distribution | All three symbols appear in a large sequence |
| Pseudo-random transitions | No consecutive symbols are equal; two symbols alternate |
| Input validation | Empty/duplicate alphabets, insufficient symbols and negative counts fail |
| Text export | Both filename prefixes and numeric content; legacy calls remain valid |
| Startup selection | Both algorithms are selected correctly, with optional export |
| Invalid configuration | Unknown algorithms and invalid pseudo-random inputs fail before hardware |
| Paired-pulse adapter | Exact 1–200 ms encoding, rejection of invalid IPIs, original library unchanged |
| MagicPy compatibility | Adapter encoding matches 0.1.6 across 10–100 ms in 0.1 ms steps |
| Profile preparation | Standard/Dual, independent A/B intensities, waveform and IPI readback |
| Generic paired conditions | Arbitrary SICI/LICI labels and preparation with 150/200 ms IPIs |
| Long-interval readback | Real MagicPy decoder with synthetic Dual replies; mismatched values block firing without rounding |
| Preparation failures | Communication/readback errors and stale preparation block firing |
| Protocol integration | Opt-in controller, invalid profiles before connections, both sequence algorithms |
| Event loop | One fire/EEG code per event, legacy path preserved, preparation failure never fires |
| Bounded recovery | Up to three preparation attempts; confirmed disarm required; counter resets after success |
| Uncertain delivery | Fire/EEG errors stop without repeating an attempted event |
| Pause/target loss | Disarm before waiting; resume reacquires target history |
| Target continuity | Prolonged/repeated losses and losses between events preserve order/index in both modes |
| Blocks | One block preserves behavior; 400/2, 12/3 and one-trial blocks preserve event order in both modes |
| Block rest | No preparation/fire while waiting; failed disarm requires R followed by G; invalid divisions fail before connections |
| Target-loss disarm block | R retries once per press; holding R, G and target recovery cannot bypass block; Ctrl+C exits |
| Cleanup | Partial startup, operator wait, Ctrl+C and normal exit release resources independently |
| Cleanup failures | Warnings visible with logging disabled; original exception preserved |
| Basic settings | Trial count, history size, ITI and legacy intensity validation before connections |

All controller/loop tests use mocks and bypass sleeps, keyboard and serial access.
They do not establish physical hardware support. Before experimental use, verify
Dual mode, waveform, pulse count, A/B amplitudes and IPI on the actual system,
including transitions from paired to single. Readback failures must be investigated,
not bypassed. Keep `MODE = "intensity"` until this validation is complete.

The hardware modules (stimulator, ESP32 trigger, neuronavigation) require the physical equipment and are verified manually in the lab.

---

## How to run

### 1. Install `uv` (if you haven't)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Install the project

From the **project root** directory:

```bash
uv sync
```

This creates a `.venv/` virtual environment and installs all dependencies listed in `pyproject.toml`, including `pytest`.

### 3. Run the tests

```bash
uv run pytest
```

All tests should pass. The total includes the existing context-tree tests and
parameterized cases for pseudo-random generation, export and startup selection.

### 4. Run with more detail (optional)

If a test fails and you want to see exactly what went wrong:

```bash
uv run pytest -v
```

The `-v` flag shows each test name and its result individually.

---

## Running the experiment

After refactoring, the experiment is run with:

```bash
uv run tms-eeg
```

This calls `src/tms_eeg/main.py:main()` — the same logic as the old `python main_controler.py`, just properly packaged.

Alternatively, you can also run:

```bash
uv run python -m tms_eeg.main
```
