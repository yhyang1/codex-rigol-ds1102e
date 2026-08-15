---
name: rigol-analyze
description: Verify and analyze one- or two-channel RIGOL DS1102E artifacts for pulse metrics, static-level qualification, or same-trigger cross-channel delay and pulse behavior. Use with metadata.json, waveform.npz, a capture, or a session directory.
---

# Rigol Analyze

Resolve the plugin root as two directories above this `SKILL.md` and use its absolute `scripts/rigol-cli` path. This skill is offline: do not access USB or alter the oscilloscope.

## Procedure

1. Run `verify --output RUN/verification.json` before analysis. Stop on hash, structure, session-terminal, accepted-count, or restore-evidence failure.
2. Use CH1 unless the user explicitly requests CH2 or cross-channel analysis.
3. Read each channel's qualification mode. For pulse mode, obtain the nominal frequency from the user, acquisition profile, or session metadata. Do not infer it from the measured waveform and then present the same comparison as an independent accuracy test. For static mode, report the saved median/mean/min/max/Vpp, matched window, rejection reasons, and `transitions_verified: false`; do not run pulse analysis on that channel.
4. For one capture run `analyze CAPTURE --channel 1 --nominal-frequency HZ`.
5. For a run directory use `analyze-series RUN --channel 1 --nominal-frequency HZ`. This writes `series-analysis.json` atomically alongside the captures.
6. Inspect boundary truncation flags before reporting glitch counts. Partial pulses at the acquisition window edges are excluded from complete-pulse metrics and are not glitches.
7. For two-channel causal timing, require both channel arrays in every capture and run `analyze-paired-series` with distinct trigger and dependent channels. Use an expectations JSON for a pass/fail decision; without it, report descriptive metrics only.

```bash
"$PLUGIN_ROOT/scripts/rigol-cli" verify "$ARTIFACT" \
  --output "$RUN/verification.json"
"$PLUGIN_ROOT/scripts/rigol-cli" analyze-series "$RUN" \
  --channel 1 --nominal-frequency 1000
"$PLUGIN_ROOT/scripts/rigol-cli" analyze-paired-series "$RUN" \
  --trigger-channel 1 --strobe-channel 2 \
  --expectations "$EXPECTATIONS_JSON"
```

## Evidence boundaries

- [COMPUTED] Frequency, period statistics, pulse widths, amplitude-outlier counts, missing cycles, and extra pulses are derived from saved samples.
- [KNOWN] Scope-reported measurements are saved instrument metadata, separate from the sample-derived calculation.
- [KNOWN] A null scope measurement is unavailable, not zero. Static/noise traces have no host frequency unless an explicit pulse analysis supplies a nominal reference.
- [KNOWN] Static qualification proves only that one saved frame's representative level matched a declared window and noise gate; it does not prove transitions or both states.
- [KNOWN] Trigger-relative phase uses the downloaded RAW-buffer origin; it is diagnostic and is not source phase against an external clock.
- [KNOWN] A single self-triggered CH1 trace cannot determine connector end-to-end delay or absolute long-term phase.
- [INFERRED] A stable ten-frame result supports repeatability over that saved interval only; it does not prove long-duration stability.
- [KNOWN] Frequency accuracy remains relative to the oscilloscope timebase unless external calibration evidence exists.
- [KNOWN] DS1102E channels sample simultaneously, while USB downloads are sequential; do not treat download timestamps as channel timing.
- [KNOWN] The manual's typical 500 ps channel delay is a specification, not a measured correction for the saved capture.

Report the exact artifact path and separate `[KNOWN]`, `[COMPUTED]`, and `[INFERRED]` statements with confidence labels.
