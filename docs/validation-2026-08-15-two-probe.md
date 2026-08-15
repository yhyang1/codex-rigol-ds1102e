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
