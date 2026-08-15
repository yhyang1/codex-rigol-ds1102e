# Evidence-first handoff — DS1102E two-probe plugin

## Objective

Review the supplied RIGOL DS1102E manual and make the Codex plugin safely and
auditably support a USB-connected oscilloscope with two probes.

## Increment Completed

- Added independent CH1/CH2 qualification with all-channel acceptance.
- Added one-trigger dual capture with selected-channel enable/restore and
  strict documented memory-depth checks.
- Upgraded capture artifacts and verification to schema version 2.
- Added the focused `rigol-use-two-probes` Skill and updated the four existing
  Skills, plugin UI, README, and bundled profile.
- Built, validated, installed, and enabled plugin version
  `0.1.0+codex.20260815050521`.
- Performed a live read-only USB preflight against serial `DS1ET183009083`.
  Identity passed, but both channels were configured as 1X and both frequency
  and Vpp measurements returned `99e36`; no configuration writes followed.
- After the user supplied the physical safety declaration, completed and
  verified dual-channel overview and pulse-detail captures. The overview proves
  9.999808684 Hz over eight PA3 pulses; the 1 MSa/s detail proves a 99.994 us
  PA3 pulse while CH2 remained at the Hall-high state near 2.81 V.
- Independently verified restoration of the original channel, trigger,
  timebase, memory, acquisition, and running state after the live captures.
- Added generic query-only `preflight`, DS1000E invalid-sentinel normalization,
  no-reference frequency suppression, and per-channel pulse/static
  qualification with explicit transition boundaries.
- Ran a live mixed pulse/static session. CH1 passed all seven frames; CH2
  matched the declared high window but correctly failed the 0.10 Vpp noise gate
  in all seven frames. The bounded session restored state and verified valid.
- Built, validated, installed, and live-tested plugin version
  `0.1.0+codex.20260815060129`.

## Evidence

See `docs/validation-2026-08-15-two-probe.md`. The final 68-test suite, five
Skill validators, canonical and packaged plugin validators, locked-runtime
package, installed command entrypoint, installed read-only preflight, and live
mixed-mode fail-closed session pass their stated acceptance boundaries.

## Files/State Changed

- Runtime: `src/rigol_tool/`
- Tests: `tests/`
- Editable profiles: `configs/`
- Plugin source: `plugin/rigol-ds1102e/`
- Design, implementation plan, validation, and handoff: `docs/`
- Generated package: `build/codex-plugin/rigol-ds1102e/`
- Personal installation: `rigol-ds1102e@personal`, enabled at version
  `0.1.0+codex.20260815060129`

## Remaining Acceptance Items

- Investigate the physical/probe/scope/DUT source of the observed CH2
  0.44–0.56 Vpp if the application requires the prior approximately 0.034 Vpp
  expectation.
- Observe a separate authorized Hall-low snapshot if evidence for the low
  window is required.
- Move the wheel through both Hall states only under separate physical-motion
  authorization if transition behavior must be proven.

The generic tool/Skill implementation and requested live validation are closed.
The items above are intentionally unproven external measurement or motion
boundaries, not missing plugin behavior.

## Blockers/Risks

- The probe ground clips are common to oscilloscope ground; unsafe differential
  placement can short the DUT.
- Physical attenuation switches and voltage/category ratings cannot be proved
  over USB.
- Two-channel LONG transfer remains deliberately unvalidated on this bench
  path; NORMAL is the default.
- Timing remains relative to the oscilloscope timebase unless calibration
  evidence is supplied.
- Physical probe switches, ground-clip locations, and signal points are known
  only through the user's safety declaration; USB readback cannot independently
  prove those physical conditions.
- CH2 was sampled only in the Hall-high state. No wheel motion was authorized,
  so Hall-low and transitions remain unproven.
- The live captures show CH2 0.44–0.48 Vpp and substantial CH1 ripple. These
  materially exceed the prior noise record and remain unexplained measurement-
  chain evidence rather than validated DUT behavior.

## Next Concrete Action

Start a new Codex task so the refreshed Skill catalog loads. Use `preflight`
before configuration writes and a workspace profile with explicit per-channel
signal modes. If continuing this bench diagnosis, isolate the CH2 measurement
chain without weakening the 0.10 Vpp gate or claiming Hall transitions.

## THE Reflection

The evidence-first method forced the implementation to preserve a correct
rejection instead of tuning thresholds until the session passed. The generic
signal-class boundary was derived from a concrete bench counterexample without
embedding that DUT into the plugin. No change to the THE Skill itself is
justified by this iteration.
