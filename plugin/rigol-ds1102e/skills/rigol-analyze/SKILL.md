---
name: rigol-analyze
description: Analyze one capture or a series of RIGOL DS1102E CH1 waveform artifacts for frequency, pulse timing, amplitude outliers, missing or extra pulses, and trigger-relative phase. Use after acquisition or when given metadata.json, waveform.npz, or a session directory.
---

# Rigol Analyze

Resolve the plugin root as two directories above this `SKILL.md` and use its absolute `scripts/rigol-cli` path. This skill is offline: do not access USB or alter the oscilloscope.

## Procedure

1. Run `verify --output RUN/verification.json` before analysis. Stop on hash, structure, session-terminal, accepted-count, or restore-evidence failure.
2. Use CH1 unless the user explicitly requests another saved channel.
3. Obtain the nominal frequency from the user, acquisition profile, or session metadata. Do not infer it from the measured waveform and then present the same comparison as an independent accuracy test.
4. For one capture run `analyze CAPTURE --channel 1 --nominal-frequency HZ`.
5. For a run directory use `analyze-series RUN --channel 1 --nominal-frequency HZ`. This writes `series-analysis.json` atomically alongside the captures.
6. Inspect boundary truncation flags before reporting glitch counts. Partial pulses at the acquisition window edges are excluded from complete-pulse metrics and are not glitches.

```bash
"$PLUGIN_ROOT/scripts/rigol-cli" verify "$ARTIFACT" \
  --output "$RUN/verification.json"
"$PLUGIN_ROOT/scripts/rigol-cli" analyze-series "$RUN" \
  --channel 1 --nominal-frequency 1000
```

## Evidence boundaries

- [COMPUTED] Frequency, period statistics, pulse widths, amplitude-outlier counts, missing cycles, and extra pulses are derived from saved samples.
- [KNOWN] Scope-reported measurements are saved instrument metadata, separate from the sample-derived calculation.
- [KNOWN] Trigger-relative phase uses the downloaded RAW-buffer origin; it is diagnostic and is not source phase against an external clock.
- [KNOWN] A single self-triggered CH1 trace cannot determine connector end-to-end delay or absolute long-term phase.
- [INFERRED] A stable ten-frame result supports repeatability over that saved interval only; it does not prove long-duration stability.
- [KNOWN] Frequency accuracy remains relative to the oscilloscope timebase unless external calibration evidence exists.

Report the exact artifact path and separate `[KNOWN]`, `[COMPUTED]`, and `[INFERRED]` statements with confidence labels.
