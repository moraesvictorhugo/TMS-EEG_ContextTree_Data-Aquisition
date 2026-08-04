# Testing Guide

This project uses [pytest](https://docs.pytest.org/) to run automated tests and [uv](https://docs.astral.sh/uv/) to manage the environment.

## What is tested?

The tests focus on the **context-tree sequence generator** — the only part of the code that can be verified without the physical lab equipment. They check:

| Test | What it verifies |
|---|---|
| Symbol transitions | After `2` → always `1`; after `(1,1)` → `0`; etc. |
| Sequence length | Output has exactly the requested number of stimuli |
| Valid symbols | Every element is `0`, `1`, or `2` |
| Distribution | All three symbols appear in a large sequence |

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

You should see output like:

```
======================== test session starts ========================
collected 9 items

tests/test_sequence.py .........                              [100%]

========================= 9 passed =================================
```

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
