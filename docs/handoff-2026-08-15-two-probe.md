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

## Evidence

See `docs/validation-2026-08-15-two-probe.md`. The full 47-test suite, five
Skill validators, canonical and packaged plugin validators, locked-runtime
package, installed command entrypoint, and installed pre-USB failure gate pass.

## Files/State Changed

- Runtime: `src/rigol_tool/`
- Tests: `tests/`
- Editable profiles: `configs/`
- Plugin source: `plugin/rigol-ds1102e/`
- Design, implementation plan, validation, and handoff: `docs/`
- Generated package: `build/codex-plugin/rigol-ds1102e/`
- Personal installation: `rigol-ds1102e@personal`, enabled at version
  `0.1.0+codex.20260815050521`

## Remaining Acceptance Items

- Normalize the DS1102E invalid measurement sentinel `99e36`/`9.9e37` to null.
- Decide and implement the mixed qualification policy for pulse CH1 plus a
  stationary Hall channel that may validly be either high or low.
- Decide whether to add a formal read-only `preflight` CLI command.
- Re-run tests, validators, packaging, installation, and live narrow checks for
  the approved tool/Skill increment.

The first four live-capture acceptance items are now closed. The items above
are the evidence-driven software/Skill increment that remains.

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

Complete brainstorming approval for the next tool increment. The recommended
scope is invalid-sentinel normalization, a formal read-only `rigol preflight`,
and mixed per-channel qualification so PA3 pulse validity can coexist with a
stationary Hall channel accepted in either declared low or high range.

## THE Reflection

The evidence-first method exposed the correct acceptance boundary: software
and installation are closed, while physical two-probe safety and live bench
capture remain explicit hardware evidence. No change to the THE Skill itself
is justified by this iteration.
