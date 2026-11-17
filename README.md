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
- `SEQUENCE_ALGORITHM` — `"context tree"` (default), `"pseudo-random"` or `"constant"`
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
retries: only preparation failures before a fire attempt may be retried, after
confirmed disarm (at most three preparation attempts per event).
Different symbols imply different intensities only when their mapped values differ.

With `EXPORT_SEQUENCE_TXT = True`, context-tree filenames retain the existing
`tree_sequence_...` prefix; pseudo-random filenames use `pseudo_random_sequence_...`.

### Constant condition

Use `constant` to repeat one condition without randomization:

```python
MODE = "intensity"
SEQUENCE_ALGORITHM = "constant"
ALPHABET = [2]
NUMBER_OF_STIMULI = 100
NUMBER_OF_BLOCKS = 1
```

This produces exactly 100 occurrences of symbol `2`, requesting the existing
`INTENSITY_MAP[2]` (`int(1.2 * RMT_INTENSITY)` in integer % MSO) and EEG code `3`
for every event. `ALPHABET` must contain exactly one integer symbol in `0–14`,
with a valid intensity/profile mapping. Invalid settings fail before connections.
For `MODE = "paired-pulse"`, the same algorithm repeats the selected `PULSE_MAP`
profile: symbol `0` is the example simple profile, while `1`/`2` are paired profiles.

Blocks, manual pause, target waiting and safety handling are unchanged. The
sequence is generated once and optionally exported as `constant_sequence_...`.
The default algorithm remains `context tree`; the pseudo-random no-repeat rule
is unchanged and is intentionally not used for a constant condition.

**Timing is unchanged:** `ITI` remains a post-event wait plus subsequent
preparation/communication and possible target waits. Setting `ITI = (4, 6)`
does not guarantee 4–6 seconds between physical pulses. No onset-to-onset
scheduling or preparation-time optimization is included in this feature.

## Experiment blocks

In the **Sequence generation** config section, set:

```python
NUMBER_OF_STIMULI = 400  # total trials, not trials per block
NUMBER_OF_BLOCKS = 2    # 2 equal blocks of 200; default 1 disables block pauses
```

Any positive number of equal, nonempty blocks is allowed. The total must be
divisible by the block count; invalid settings fail before equipment connections.
The full sequence is generated/exported once. Block boundaries do not reset
context-tree history, pseudo-random order or the global event index. Paired
events still count as one trial each.

After each internal boundary (including the last trial's normal ITI), the
stimulator is disarmed and the session waits indefinitely for **G**. Release
G and press it again if already held. Resume requires reacquiring target history
and preparing the next event. There is no programmed rest duration and no pause
after the final block. B/G manual pause and target-loss waiting remain available.

If block-boundary disarm is not confirmed, firing is blocked: **R** retries the
disarm; once confirmed, **G is still required** to start the next block. Ctrl+C
exits through normal cleanup. Rest periods emit no extra EEG codes. Continuity
is in memory only, not a restart/recovery mechanism after exiting Python.

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
individually synchronized A/B onsets. Existing software-trigger jitter remains.
An exception during or after an attempted fire stops the sequence without
repeating that event: delivery may be uncertain. Requested profiles are printed at startup and per event; use actual device
records/measurements to confirm delivery. Preparation adds response/readback time
in addition to the original waits; ITI remains the post-event wait, not a precise
onset-to-onset trial interval.

If `set_mode` or `set_waveform` returns a MagicPy error (including `Empty`),
the paired controller requests fresh command-09 settings. Preparation continues
only if the readback succeeds and matches the requested mode, current direction
and IPI; waveform changes also require a matching waveform. Error payloads are
never treated as confirmation. A failed or mismatched readback reports both the
original command error and the independent check failure, without arming/firing.
This distinguishes a missing set acknowledgement from settings the device did
not apply; it does not establish Dual support on a particular device.

In paired-pulse mode, an `arm` error also requires a fresh status query.
Only a successful response with `Status: Enabled` allows preparation to
continue. This handles a missing acknowledgement when enabling an already
enabled device, without assuming its state from the previous event. Failed
queries, error payloads and `Disabled` status still block firing. The existing
amplitude, mode and IPI checks remain in place. `Enabled` is not proof of
charge readiness or physical delivery. With `ENABLE_LOGGING = True`, recovery
prints `Arm confirmed by independent Enabled status readback.`

## Testing

### Minimal safety layers (both modes)

- Preparation failures allow at most **three total attempts per event**, with the
  existing two-second retry wait and confirmed disarm before retrying.
- Any error during/after a fire attempt (including EEG marking) stops the session;
  it does not resend the pulse or claim that delivery did not occur.
- Failed disarm after preparation/fire errors stops retries; warnings remain
  visible with logging disabled. Target-loss waiting has the recovery below.
- Entering pause and losing target immediately before firing attempt disarm.
  Resume clears target history and requires reacquiring the existing gate.
- Coil out of target is an operational wait, not a preparation failure: the
  original sequence/index remain in memory, without consuming retry attempts.
  Once stable on target again, the same pending event is prepared and delivered.
  If disarm after target loss is not confirmed, the session stays open but firing
  is blocked. Check the device and press **R** to retry disarm once; release and
  press again if needed. G or target recovery alone cannot bypass this block.
  MagicPy 0.1.6 can report a reply-length error on disable, or `Empty` when
  already disabled. On a command error, the controller issues a fresh status
  query and accepts recovery only with error code zero and `Status: Disabled`.
  Error payloads containing `Disabled` alone do not release the block.
  Confirmed disarm returns to the normal target gate at the same event. Ctrl+C
  still exits. This is in-process continuity, not recovery after restarting Python.
- Normal exit, Ctrl+C, startup failures and operator-wait interruptions attempt
  stimulator disarm/disconnect, trigger close and tracker stop independently.
  Closing a serial port is not proof of physical disarm; inspect the device if
  acknowledgement fails. Software cleanup cannot handle power loss or forced kill.
- Invalid trial count, target history size, ITI, actual symbols and legacy
  intensities fail before opening equipment connections.

Reported reference equipment: X100 + Option, C-B70; GUI 7.2.5, PIC1 5.5.2,
PIC2 4.0.0, Nimbus 2.0.4. This records operator-provided identification, not a
certification of firmware compatibility or physical safety. Normal preparation,
post-event ITI, sequence algorithms and EEG codes are unchanged. No thermal
limits, automatic reconnection or session recovery are implemented here.

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
| `R` | Retry unconfirmed disarm after target loss; never fires or skips an event |
