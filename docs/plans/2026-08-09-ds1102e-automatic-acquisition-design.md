# DS1102E automatic acquisition design

## Decisions

- Use a local Python CLI managed by uv.
- Use PyVISA-py over PyUSB/libusb; direct USBTMC is only a fallback.
- Capture RAW deep memory from a fresh SINGLE trigger.
- Preserve raw bytes, converted arrays, metadata, and a preview.
- Restore all modified, queryable oscilloscope state on every catchable exit.
- Serialize timed captures; never access one instrument concurrently.

## Data flow

`CLI -> configuration validation -> VISA/USBTMC -> acquisition state machine ->
legacy waveform parser -> atomic NPZ/JSON/PNG bundle`

## Acceptance gates

1. Offline parser, state-machine, scheduler, and artifact tests.
2. Unique USB discovery and an exact real `*IDN?` response.
3. One real deep-memory capture with verified state restoration.
4. Repeated fresh-trigger timed captures plus verified timeout recovery.
5. A 10-minute CH1 run for frequency stability, missing/extra pulses, and
   acquisition-boundary amplitude behavior.

## CH1-only measurement boundary

- Supported: waveform-derived frequency, period jitter, pulse width,
  missing/extra pulse detection, and amplitude outliers.
- Unsupported: connector end-to-end delay, because CH2 is intentionally not
  connected.
- Unsupported: absolute long-term phase, because CH1 self-triggering supplies
  no independent reference and the legacy RAW buffer origin is not a stable
  phase datum.
