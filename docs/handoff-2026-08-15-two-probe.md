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

- Run the declared safety gate with the actual two probes.
- Execute a fresh two-probe USB `session` with both signals present.
- Verify restoration and artifacts, then run the appropriate independent or
  paired analysis.

These are hardware acceptance items, not missing software implementation.

## Blockers/Risks

- The probe ground clips are common to oscilloscope ground; unsafe differential
  placement can short the DUT.
- Physical attenuation switches and voltage/category ratings cannot be proved
  over USB.
- Two-channel LONG transfer remains deliberately unvalidated on this bench
  path; NORMAL is the default.
- Timing remains relative to the oscilloscope timebase unless calibration
  evidence is supplied.
- The physical probe switches, ground-clip locations, and signal points remain
  undeclared. The 10X template contradicts the current 1X channel readbacks,
  and neither channel currently exposes a measurable signal. Actual acquisition
  must remain blocked before USB writes.

## Next Concrete Action

Declare each probe's physical connection and 1X/10X switch position, confirm
both ground clips are on the same circuit-ground potential, and confirm the
expected signal is within probe/scope ratings. Then select or create a matching
profile and invoke `$rigol-use-two-probes` before allowing USB writes.

A possible tool increment is a formal read-only `rigol preflight` command that
emits the identity, CH1/CH2 readbacks, trigger/acquisition state, and current
measurements. This remains a design proposal only; the brainstorming approval
gate has not been satisfied and no implementation was started.

## THE Reflection

The evidence-first method exposed the correct acceptance boundary: software
and installation are closed, while physical two-probe safety and live bench
capture remain explicit hardware evidence. No change to the THE Skill itself
is justified by this iteration.
