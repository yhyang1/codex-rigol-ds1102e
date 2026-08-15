# Generic mixed-channel qualification and preflight design

## Objective

Improve the general RIGOL DS1102E CLI and Codex Skills using evidence from the
live two-probe validation. Support any acquisition in which selected channels
have different signal classes, especially a periodic pulse on one channel and
a stationary level on another. Do not encode PA3, Hall sensors, Dooroute pins,
or bench-specific voltage limits in runtime defaults or plugin assets.

## Live evidence motivating the increment

The 2026-08-15 two-probe run proved that the existing synchronized capture,
artifact verification, and restoration path works on a physical DS1102E. It
also exposed three general defects:

1. The instrument's invalid measurement sentinel `99e36`/`9.9e37` is preserved
   as a large numeric value instead of absence.
2. Host metadata infers a frequency from unqualified static-channel noise when
   no trustworthy frequency reference exists.
3. Two-channel `session` assumes every selected channel contains a periodic
   pulse, so it cannot qualify a valid mixed pulse/static acquisition.

The temporary read-only USB queries also demonstrated that identity alone is
not enough for a safe declaration: Codex needs a stable read-only command that
reports the current per-channel and trigger/acquisition readbacks before any
configuration write.

## Scope boundaries

The increment adds generic signal-class configuration, read-only preflight,
measurement normalization, tests, documentation, plugin packaging, and live
validation. It does not:

- introduce DUT-specific profiles into the plugin;
- move probes, rotate machinery, or command an actuator;
- claim that a static sample proves transitions;
- infer electrical safety from USB readback;
- add a generic expression language or arbitrary user code to qualification;
- change paired edge-timing analysis.

## Configuration model

Extend each `QualificationConfig` with a `mode`:

- `pulse` is the default and preserves current profiles and behavior.
- `static` checks that a robust representative level lies inside one of one or
  more explicit allowed voltage windows.

Static mode uses a TOML array of two-element arrays:

```toml
[qualification.channel2]
mode = "static"
allowed_level_windows_v = [
  [-0.05, 0.08],
  [2.60, 3.10],
]
max_vpp_v = 0.10
```

Rules:

- `allowed_level_windows_v` is required and non-empty for `static`.
- Every window contains two finite values with lower strictly less than upper.
- Windows must be ordered and non-overlapping so the matched state is
  deterministic.
- Pulse-only fields may remain inherited for backward compatibility but are
  ignored by static assessment; documentation must make this explicit.
- `min_vpp_v` is not applied in static mode because a stable channel is
  expected to have low variation.
- `max_vpp_v` remains an optional hard full-span noise gate.

No bench-specific default windows are provided. Users must declare voltage
windows in their workspace profile.

## Static assessment

For a selected static channel:

1. Require a non-empty finite one-dimensional voltage array.
2. Compute median voltage, minimum, maximum, mean, and full-span Vpp.
3. Match the median against the configured windows using inclusive bounds.
4. Reject with `static_level_outside_allowed_windows` when no window matches.
5. Reject with `vpp_above_maximum` when configured and exceeded.
6. Return the matched window index and bounds in the qualification metrics.
7. Always return `transitions_verified: false`; static qualification does not
   inspect or require state changes.

`assess_channels` remains all-selected-channels fail-closed. Pulse and static
results share the current event and capture metadata envelope, so no second
session state machine is introduced.

## Measurement normalization

Create one parser for optional numeric instrument measurements. It returns
`None` for:

- responses beginning with `>` or `<`;
- non-finite values;
- magnitude at or above `1e30`, including DS1000E `99e36` sentinels.

Use it for frequency and Vpp queries in both acquisition and preflight.

`waveform_statistics` will report host frequency only when a finite, positive,
sub-`1e30` reference frequency is supplied. Without a reference it still
reports minimum, maximum, mean, and Vpp, but returns frequency `None`. Explicit
analysis with a user-supplied nominal frequency remains the authoritative route
for pulse frequency when the scope measurement is unavailable.

## Read-only preflight

Add:

```text
rigol preflight [--resource ...] [--serial ...] [--channels 1,2]
```

The command opens the selected DS1102E, verifies identity, and performs queries
only. JSON output contains:

- resource and full identity;
- trigger status;
- acquisition memory/type and timebase scale/offset;
- trigger mode and, when EDGE, source/slope/level/coupling;
- for each selected channel: display, probe attenuation, coupling, vertical
  scale, offset, and normalized frequency/Vpp measurements.

The implementation must make query-only behavior testable with a fake
instrument whose `write` method fails. Preflight does not prove physical probe
switches, ground placement, or voltage/category safety; Skills must continue to
obtain those declarations from the user before configuration writes.

## Skill behavior

- `rigol-acquire` and `rigol-use-two-probes` run `preflight` after declaring the
  intended instrument/channels and before applying a workspace profile.
- They compare declared physical attenuation with both the current readback and
  the intended profile, while explaining that the intended profile may safely
  change the scope setting only after physical confirmation.
- Mixed sessions describe every channel's configured mode and require all
  selected channels to qualify.
- Static output names the matched window and states that transitions were not
  verified.
- The Skills use DUT-specific profiles only from the user's workspace; the
  bundled examples remain generic/reference-oriented.

## Error handling

- Unsupported mode or malformed/static overlapping windows fail during config
  loading before USB access.
- Static mode without explicit windows fails during config loading.
- Missing selected channels fail as today.
- Invalid instrument measurements become null, not transport errors.
- Preflight identity or transport failures use existing stable exit codes.
- Static noise above its configured maximum rejects the frame rather than
  widening thresholds automatically.

## Tests and acceptance

1. Existing pulse profiles and all prior tests remain green.
2. Config tests cover valid multiple windows, missing windows, inverted values,
   overlap, non-finite values, and unsupported modes.
3. Static assessment accepts either declared window, identifies the matched
   window, rejects an intermediate level, and rejects excessive Vpp.
4. Mixed assessment accepts only when both pulse and static channels pass.
5. Measurement parser tests cover normal numbers, comparison-prefixed values,
   non-finite values, and `99e36`.
6. Metadata no longer reports an inferred frequency for an unreferenced static
   trace.
7. Preflight tests prove exact selected-channel JSON and zero writes.
8. Full tests, all Skill validators, canonical/packaged plugin validators, and
   packaged CLI help pass.
9. Installed-plugin live preflight returns normalized null measurements.
10. A live mixed session is attempted with user-declared safe wiring. It must
    either complete with valid artifacts and restoration or reject with exact
    per-channel reasons; rejection is valid evidence and thresholds are not
    weakened to force a pass.

## Approved interpretation boundary

The motivating PA3/Hall capture is an example, not a product-specific target.
Completion means the generic CLI and Skills can safely express, acquire,
qualify, and report mixed signal classes on arbitrary DS1102E channels while
preserving explicit physical and measurement-evidence boundaries.
