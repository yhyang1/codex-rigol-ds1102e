# DS1102E CH1 bench validation — 2026-08-09

## Instrument and transport

- Identity: `Rigol Technologies,DS1102E,DS1ET183009083,00.04.02.01.00`
- Transport: PyVISA-py / PyUSB / libusb over USBTMC
- Channel: CH1 only
- Current connected source: front-panel probe compensator output
- Official typical output: 1 kHz, approximately 3 Vpp
  ([RIGOL DS1000E User's Guide](https://www.rigol.com/dam/global/downloads/brochures/en/user-manual/oscilloscopes/DS1000E_UserGuide_EN.pdf))
- CH1 probe-menu attenuation: 1x
- Deep capture: 524,288 samples at 100 MHz

## Fresh-trigger proof

The acquisition state machine rejects the pre-arm stale `STOP` state. It must
observe `RUN` or `WAIT` before accepting the subsequent `STOP` as a completed
single trigger.

- One aligned proof capture:
  `captures/probe-comp-1x-final/20260809T072523.219636Z_000001`
- Waveform-derived result: 1000.005000 Hz, 3.00 V high level, 3.04 Vpp,
  approximately 50% duty cycle.
- The scope's built-in frequency query returned 992 Hz for that frame, so the
  downloaded-waveform estimate is used for precision analysis.

## Timeout and restoration

An EXT-trigger profile with no connected EXT signal produced the expected
`WAIT` timeout. `captures/timeout-test-v14` reported only the timeout; a
separate readback confirmed CH1, 2 V trigger level, NORMAL sweep, NORMAL memory,
and running acquisition were restored.

Firmware 00.04.02 query responses cannot always be written back verbatim:
`CH1` must be written as `CHAN1`, trigger sweep `NORMAL` as `NORM`, and queried
scientific-notation numerics must be converted to ordinary decimal setters.
`captures/nonzero-offset-restore-proof` additionally verified that a queried
`-8.186e-05` time offset is written back and restored correctly; the bench was
then explicitly returned to 0 s offset and running acquisition.

## Ten-minute aligned CH1 run

Artifact: `captures/probe-comp-1x-long-10min/series-analysis.json`

- 21/21 captures succeeded over 600.136755 s.
- Mean waveform-derived frequency: 1000.0012202518 Hz.
- Standard deviation across captures: 0.0034957333 Hz.
- Range: 999.9950000250 to 1000.0075000563 Hz.
- Relative error against nominal 1 kHz: +1.220252 ppm.
- Missing cycles: 0.
- Extra pulses: 0.
- Complete-pulse peak-amplitude outliers: 0.
- All 21 captures began inside a high-level pulse; those leading partial pulses
  are reported as window-boundary truncations and excluded from glitch and
  frequency statistics.

The trigger-slot pulse mean was 3.000 V. Neighboring complete-pulse slots were
3.000 to 3.0019 V. This run does not show a systematic acquisition start/stop
amplitude glitch.

## Accuracy and phase boundary

The frequency estimate is precise relative to the DS1102E sampling timebase,
but it is not a traceable absolute-frequency calibration. A calibrated external
reference is required for that claim.

The RAW-buffer-relative phase diagnostic spanned 0.03114 degrees over the
ten-minute run, with a 0.00686-degree standard deviation. It is repeatable in
this setup but is not an absolute long-term source-phase measurement. CH1
self-triggering has no independent phase reference, and CH1 alone cannot
measure connector end-to-end phase delay.

## Superseded source record

Earlier artifacts under `captures/long-run-10min` measured the previously
connected nominal 60 Hz source. They remain auditable but are not the acceptance
record for the current front-panel probe-compensation connection.
