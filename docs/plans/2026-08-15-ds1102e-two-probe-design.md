# DS1102E two-probe Codex workflow design

## Objective

Extend the existing RIGOL DS1102E Codex plugin from a CH1-oriented workflow to
a safe, auditable two-probe workflow over USB. Preserve the validated
single-channel path while supporting both independent channel analysis and
same-trigger CH1/CH2 timing analysis.

## Evidence basis

Primary references:

- Supplied local manual: `/Users/yangmeng/Downloads/9d3641.pdf` (174 pages,
  reviewed in rendered form during this iteration).
- Official RIGOL DS1000E/DS1000D User's Guide:
  <https://www.rigol.com/dam/global/downloads/brochures/en/user-manual/oscilloscopes/DS1000E_UserGuide_EN.pdf>
- Official RIGOL DS1000E/DS1000D Programming Guide:
  <https://eu.rigol.com/eu/Images/DS1000E_ProgrammingGuide_EN_tcm30-2863.pdf>

- The supplied DS1000E/DS1000D User's Guide identifies the DS1102E as a
  two-channel oscilloscope. It requires the attenuation setting of each channel
  to match its physical probe and states that probe ground terminals share the
  oscilloscope ground potential.
- The User's Guide specifies that dual-channel acquisition is simultaneous and
  reduces Normal record length to 8 Kpts, Long record length to 512 Kpts, and
  the maximum real-time sample rate to 500 MSa/s. Typical inter-channel delay is
  500 ps.
- The official DS1000E/DS1000D Programming Guide documents VISA USB access,
  per-channel configuration, `:WAV:DATA? CHAN1|CHAN2`, RAW waveform mode, and
  the 8,192/524,288-point dual-channel RAW depths.
- The existing bench record validates identity checks, fresh SINGLE triggering,
  generic TMC block parsing, NORMAL-memory reliability, artifact hashing, and
  restoration on serial `DS1ET183009083`, firmware `00.04.02.01.00`.

The supplied User's Guide is not a programming reference. SCPI details are
therefore bounded by the official Programming Guide and existing real-device
readback evidence rather than inferred from the User's Guide.

## Safety boundary

Before USB writes, Codex must declare the selected serial, channels, trigger
source, profile, output directory, and physical attenuation expected for each
probe. A two-probe workflow must require the user to confirm that:

1. each probe's physical switch and oscilloscope channel attenuation agree;
2. both ground clips are connected only to the same circuit ground potential;
3. the measured voltage and probe category remain within the probe and
   oscilloscope ratings.

The plugin does not move probes, change wiring, energize the DUT, or infer that
two ground points are equipotential. USB automation may configure and restore
the oscilloscope only.

## Acquisition architecture

Keep one VISA/USBTMC connection and one `CaptureSession`. For a selected
two-channel acquisition:

1. Snapshot the original state of both selected channels.
2. Temporarily enable CH1 and CH2 and verify both display-state readbacks.
3. Apply independent coupling, probe attenuation, vertical scale, offset, and
   bandwidth limit settings.
4. Arm one fresh SINGLE trigger and wait for the required armed-to-STOP
   transition.
5. Query the common sample rate and timebase once.
6. Query each channel's memory depth and require the dual-channel depth expected
   for the selected memory mode.
7. Download CH1 and CH2 sequentially from the same stopped acquisition buffer.
8. Require equal point counts and build one shared time axis.
9. Save both raw byte arrays, both converted voltage arrays, the common time
   axis, transfer order, and per-channel readbacks.
10. Restore and verify all modified settings and the original run state.

The artifact language must say "simultaneously sampled, sequentially downloaded"
and must not call USB transfer simultaneous.

## Qualification model

Preserve the current flat `[qualification]` section for backward-compatible
single-channel sessions. Add optional `[qualification.channel1]` and
`[qualification.channel2]` subsections with independent nominal frequency, Vpp,
minimum complete-pulse, and period-CV gates.

When two channels are selected, a frame is accepted only when both selected
channels pass their configured gates. Status events and saved metadata contain
per-channel results. A failure or transport reconnect resets the shared
consecutive-frame contact gate. This prevents a healthy CH1 trace from
promoting an absent or invalid CH2 trace.

## Artifacts and verification

Each capture remains one atomic directory containing:

- `waveform.npz` with one common `time_s` and CH1/CH2 raw and voltage arrays;
- `metadata.json` with instrument identity, acquisition mode, transfer order,
  sample rate, timebase, selected channels, and independent channel settings;
- `preview.png` showing both labeled waveforms;
- SHA-256 evidence for the NPZ file.

Verification must fail closed when selected-channel metadata and arrays differ,
when any raw/voltage/time array length differs from `point_count`, when the two
channels do not share one time axis, or when a completed two-channel session
does not contain both channels in every accepted capture.

## Analysis and Codex Skills

Retain single-channel `analyze` and `analyze-series`. Retain
`analyze-paired-series` for causal pulse pairs in either CH1-to-CH2 or
CH2-to-CH1 direction.

Update the existing acquisition, analysis, interpretation, and end-to-end
Skills so their descriptions and procedures cover one or two probes. Add a
focused `rigol-use-two-probes` Skill that owns the physical safety confirmation,
dual-contact qualification, synchronized capture, verification, and selection
between independent and paired analysis.

Interpretation must preserve these boundaries:

- sample-derived timing is relative to the oscilloscope timebase unless
  external calibration evidence exists;
- the typical 500 ps channel delay is a specification, not a per-capture
  correction or measured value;
- sequential USB download does not change the shared acquisition timebase;
- saved windows are disjoint unless continuous acquisition is separately
  proven;
- two probes prove only the two physical probe points.

## Failure handling

- Refuse duplicate or unsupported channel selections.
- Refuse two-channel sessions without independent qualification definitions.
- Refuse a selected channel whose display state cannot be enabled and verified.
- Treat unequal channel depths or payload sizes as waveform corruption.
- Treat a waveform transfer failure as transport loss and reconnect rather than
  reusing a broken session as completion evidence.
- Never report safe completion unless restoration and artifact verification are
  both valid.

## Acceptance evidence

1. Existing single-channel tests continue to pass.
2. New tests prove both selected channels are enabled, captured from one STOP
   event, saved with one time axis, and restored.
3. New tests reject weak CH2 contact when CH1 is valid.
4. New tests reject unequal or incomplete dual-channel artifacts.
5. Paired analysis tests remain green in both channel directions.
6. All Skill folders and the plugin manifest pass their validators.
7. The packaged plugin contains the two-probe profile, runtime changes, and new
   Skill.
8. USB bench acceptance remains pending until two safely connected probes are
   available and the user authorizes the declared configuration writes.
