# DS1102E two-probe validation — 2026-08-15

## Scope

This record validates the software/plugin increment for USB-controlled,
same-trigger CH1/CH2 acquisition with two probes. It does not claim a new live
two-probe bench run.

## Manual evidence used

- The supplied 174-page DS1000E/DS1000D manual was inspected in rendered form,
  including the channel probe setting, acquisition/memory, storage, and
  specification pages.
- The user manual establishes a two-channel instrument, per-channel probe
  attenuation, a common probe-ground potential, simultaneous dual-channel ADC
  acquisition, 8 Kpts/channel in Normal memory, 512 Kpts/channel in Long
  memory, and a typical 500 ps channel-to-channel delay specification.
- The official programming guide establishes VISA USB access, per-channel SCPI
  commands, `:WAV:DATA? CHAN1|CHAN2`, RAW transfer, and exact dual-channel RAW
  counts of 8,192 or 524,288 points.
- User manual:
  <https://www.rigol.com/dam/global/downloads/brochures/en/user-manual/oscilloscopes/DS1000E_UserGuide_EN.pdf>
- Programming guide:
  <https://eu.rigol.com/eu/Images/DS1000E_ProgrammingGuide_EN_tcm30-2863.pdf>

## Executed evidence

| Check | Result |
|---|---|
| Full unit suite | PASS; 47 tests collected and all completed with exit code 0 |
| Skill validation | PASS; all five canonical Skill folders |
| Canonical plugin validation | PASS |
| Locked-runtime package | PASS; `uv sync --frozen --no-dev --no-editable` installed 16 packages |
| Packaged plugin validation | PASS |
| Packaged command entrypoint | PASS; `rigol --help` exited 0 |
| Packaged two-probe asset | PASS; byte-identical to canonical config |
| Packaged two-probe Skill | PASS; file present |
| Personal plugin installation | PASS; installed and enabled as `0.1.0+codex.20260815050521` |
| Installed fail-closed gate | PASS; dual `session` without nested CH1/CH2 qualification exited 2 before USB |

## Behaviors covered by tests

- Existing single-channel behavior remains covered.
- Duplicate channel selections fail.
- Selected CH1 and CH2 are enabled, acquired in deterministic transfer order,
  and restored to their original display states.
- Dual Normal-memory readback must be exactly 8,192 points per channel.
- Both channels must pass independent qualification before a frame is promoted.
- A dual session without explicit per-channel qualification fails before USB
  connection.
- Schema-v2 captures preserve selected channels, transfer order, and the
  simultaneously-sampled/sequentially-downloaded boundary.
- Artifact verification rejects missing channels, array-length mismatches,
  invalid time axes, and session-wide channel inconsistency.
- Paired analysis works with either channel assigned as trigger.

## Unclosed hardware acceptance

No new USB acquisition was run with two physically connected probes. Hardware
acceptance therefore remains pending until the user declares the instrument
serial, probe attenuation switches, common-ground wiring, voltage/category
limits, signal roles, trigger source, profile, and output directory. The
software must not convert the manual's typical 500 ps specification into a
measured correction.

## Live read-only preflight — 2026-08-15 13:13 +0800

No configuration write or waveform capture was attempted. Read-only USB
evidence from serial `DS1ET183009083` established:

- identity: `Rigol Technologies,DS1102E,DS1ET183009083,00.04.02.01.00`;
- CH1 and CH2 were both displayed, DC-coupled, and configured as 1X at
  1 V/div;
- current acquisition mode was NORMAL and trigger mode was CH1 EDGE;
- `:MEAS:FREQ?` and `:MEAS:VPP?` returned `99e36` for both channels, so no
  valid signal measurement was available;
- the checked-in two-probe template requires 10X on both channels and therefore
  was not safe to apply without physical attenuation confirmation.

The run is blocked before configuration writes. The smallest input needed is a
physical declaration of each probe's connection and 1X/10X switch position,
plus confirmation that both ground clips are on the same circuit-ground
potential and the signal is within the probe/scope ratings.

## Live two-probe acquisition — 2026-08-15 13:32–13:36 +0800

The user subsequently declared both physical probes at 1X, both ground clips
on the same digital GND, CH1 on PA3, and CH2 on PD15/Hall A. Expected signals
were a 10 Hz PA3 pulse approximately 96–112 us wide and a stationary Hall level
near either 0 V or 2.76–2.80 V. The highest expected voltage was below 3 V.

All captures used serial `DS1ET183009083`, dual-channel NORMAL memory, CH1 EDGE
triggering, and one common time axis. Each capture contained 8,192 points per
channel and passed schema-v2 artifact verification.

### Overview capture

- Artifact:
  `captures/bench-two-probe-pa3-hall-20260815/overview/20260815T053219.428770Z_000001`
- NPZ SHA-256:
  `98fb9b1ddb981fb2d59f68a441e9745b7053b7bc8d557b4680a47de3c682da78`
- Configuration: CH1 0.2 V/div, CH2 1 V/div, 20 ms/div, CH1 rising trigger
  at 0.2 V.
- Readback: 10 kSa/s, 8,192 points, approximately 819.2 ms total record.
- CH1 analysis against 10 Hz: eight rising edges, 9.999808684 Hz,
  100.001913 ms mean period, no missing or extra pulses.
- CH1 interpolated mean width was 112.523 us, but the 100 us sample interval is
  too coarse for an authoritative width measurement.
- CH2 remained high with mean 2.8127 V, range 2.60–3.04 V, and 0.44 Vpp.

### Noise-trigger diagnostic capture

- Artifact:
  `captures/bench-two-probe-pa3-hall-20260815/detail/20260815T053331.073980Z_000001`
- NPZ SHA-256:
  `ce17f3113f5e7860e1763bf34b41c2a5bbe468eac6efba7c695981099fcd1f70`
- Configuration: 0.2 ms/div and CH1 trigger at 0.2 V.
- The 1 MSa/s record contained 533 hysteretic noise edges and no valid 10 Hz
  period. This capture does not measure the PA3 pulse; the trigger threshold was
  below the observed ripple peaks.

### Corrected pulse-detail capture

- Artifact:
  `captures/bench-two-probe-pa3-hall-20260815/detail-signal/20260815T053617.936582Z_000001`
- NPZ SHA-256:
  `953521469a5c1f3547a6f7fb39d6c993ce0b90561ee5aec7f836620c79f18e24`
- Configuration: 0.2 ms/div and CH1 trigger raised to 0.55 V.
- Readback: 1 MSa/s, 8,192 points, 1 us sample interval.
- CH1 contained one target pulse with -0.040 V estimated baseline, 0.880 V
  peak, and 99.994 us interpolated width. One pulse cannot independently
  estimate frequency, so frequency authority remains the overview capture.
- CH2 remained high with mean 2.8129 V. Host RAW conversion reported a
  2.56–3.04 V range and 0.48 Vpp; the scope reported 0.44 Vpp.

### Restoration and interpretation boundary

After both accepted captures, independent readback matched the pre-capture
channel, trigger, timebase, memory, and acquisition settings: CH1/CH2 1X and
1 V/div, CH2 offset 40 mV, CH1 trigger 60 mV, 200 ms/div, NORMAL memory, and
NORMAL acquisition. Trigger status was running after restoration, consistent
with the pre-capture non-STOP state.

The captures prove a same-trigger PA3 pulse and stationary Hall-high sample.
They do not prove Hall transitions or Hall-low behavior. The observed Hall
0.44–0.48 Vpp and CH1 high-frequency ripple materially exceed the user's prior
noise record and remain a probe/scope/DUT measurement-chain anomaly. The
metadata also preserves invalid scope measurement sentinel `9.9e37` as a
numeric value; this is a confirmed tool defect to fix in the next approved
increment.
