# DS1102E two-probe implementation plan

## Increment 1: configuration and qualification

- Extend `src/rigol_tool/config.py` with per-channel qualification parsing while
  keeping flat single-channel profiles compatible.
- Extend `src/rigol_tool/session.py` with an all-selected-channels assessment.
- Update CLI session events and metadata to carry per-channel gate results.
- Add configuration and qualification tests, including valid CH1 plus invalid
  CH2 rejection.

## Increment 2: synchronized dual capture and verification

- Make `CaptureSession` temporarily enable every selected channel and restore
  its original display state.
- Record selected channels, acquisition mode, and transfer order.
- Strengthen capture invariants for equal channel point counts and documented
  dual-channel memory depth.
- Strengthen `verify.py` to validate all time/raw/voltage arrays and session-wide
  channel consistency.
- Add dual-channel acquisition, restoration, artifact, and corruption tests.

## Increment 3: plugin surface

- Add an editable two-probe TOML profile to `configs/` and the plugin assets.
- Update the four existing Skills for one/two-channel routing.
- Add `rigol-use-two-probes` with the mandatory grounding and attenuation gate.
- Regenerate or update `agents/openai.yaml` and revise plugin UI metadata.
- Update README usage and evidence boundaries.

## Increment 4: verification and handoff

- Run the full unit suite with the locked environment.
- Run `quick_validate.py` for every Skill.
- Update the plugin cachebuster, validate the canonical plugin, package it, and
  validate the packaged plugin.
- Inspect the final diff and repository status.
- Record the evidence-first handoff, including the explicit boundary that no
  new two-probe USB bench run has been performed without a declared safe setup.

