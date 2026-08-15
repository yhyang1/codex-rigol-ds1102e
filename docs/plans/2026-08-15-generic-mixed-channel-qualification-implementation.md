# Generic mixed-channel qualification implementation plan

## Increment 1: normalize instrument measurements

- Add a shared optional-measurement parser in `instrument.py`.
- Replace capture-local response parsing with the shared parser.
- Make `waveform_statistics` return no frequency without a trustworthy
  reference.
- Add unit tests for DS1000E sentinel, comparison-prefixed, non-finite, normal,
  and unreferenced-static cases.

Narrow verifier: waveform, artifact, and instrument tests.

## Increment 2: add read-only preflight

- Add a query-only preflight function in `instrument.py`.
- Add `preflight --channels` to `cli.py` using the existing identity and
  connection selection behavior.
- Return stable JSON with acquisition, trigger, timebase, and per-channel
  readbacks plus normalized measurements.
- Add a fake instrument that raises on any write and verify zero writes.

Narrow verifier: CLI/instrument preflight tests and installed-style `--help`.

## Increment 3: add generic static qualification

- Extend `QualificationConfig` and TOML parsing with `mode` and finite,
  ordered, non-overlapping `allowed_level_windows_v`.
- Keep `pulse` as the default for backward compatibility.
- Route `assess_capture` to pulse or static assessment.
- Emit static metrics including matched window and
  `transitions_verified: false`.
- Preserve all-channel fail-closed behavior in mixed sessions.
- Add config, static assessment, mixed pass/fail, and event-payload tests.

Narrow verifier: config and session tests.

## Increment 4: update generic plugin guidance

- Update README and acquisition/two-probe/analysis/interpretation/workflow
  Skills for preflight, mixed modes, and static interpretation boundaries.
- Do not add PA3/Hall-specific bundled assets or defaults.
- Update Skill UI descriptions only where routing materially changes.
- Refresh the plugin cachebuster after all source edits.

Narrow verifier: every Skill validator and canonical plugin validator.

## Increment 5: broad verification and live evidence

- Run the complete unit suite.
- Package with the frozen non-development runtime.
- Validate the packaged plugin and command entrypoint.
- Install and confirm the refreshed personal plugin version.
- Run installed `preflight` against `DS1ET183009083`; require normalized nulls
  instead of `9.9e37` where measurements are invalid.
- Create a workspace-only mixed pulse/static profile using the declared bench
  values; do not bundle it as a generic plugin asset.
- Run a bounded mixed session. Accept either successful qualified captures or
  exact fail-closed per-channel rejection as evidence; do not widen gates to
  manufacture a pass.
- Verify the resulting artifacts and restoration when a capture is promoted.

## Increment 6: handoff and commit

- Update validation and evidence-first handoff documents with exact commands,
  paths, hashes, test counts, live results, limitations, and next action.
- Inspect final diff and worktree status.
- Commit the coherent implementation and documentation.
- Do not push without a separately authorized delivery route.
