---
name: rigol-interpret
description: Interpret verified RIGOL DS1102E acquisition and analysis artifacts and write an evidence-bounded Markdown report. Use when the user asks what a waveform means, whether glitches occurred, how precise the reading is, or wants interpretation.md.
---

# Rigol Interpret

Interpret artifacts; do not invent additional measurements. This skill does not access USB.

## Inputs and checks

Read `metadata.json`, `events.jsonl`, verification output, and `series-analysis.json` when present. If series analysis is absent, use the `rigol-analyze` skill first. Trace every numerical statement to a saved field or an explicit calculation.

## Required output

Write the report beside the analyzed run as `interpretation.md`. Never overwrite an existing report; use `interpretation-YYYYMMDDTHHMMSSZ.md` instead. Return the same conclusions in chat and link the report.

Use exactly these report sections:

1. `Evidence` — instrument identity, profile, CH1-only scope, timestamps, capture count, qualification and restoration evidence.
2. `Computed Results` — frequency distribution, error relative to the declared nominal, complete-pulse glitch totals, pulse/amplitude findings, and trigger-relative phase diagnostics.
3. `Interpretation` — bounded conclusions supported by those results.
4. `Limitations` — scope timebase calibration, sample interval, trigger-relative phase reference, single-channel limits, and duration limits.
5. `Artifact Index` — relative links to verification, event, metadata, waveform, analysis, and report artifacts.

## Interpretation rules

- Tag every factual sentence `[KNOWN]`, every numeric derivation `[COMPUTED]`, and every deduction `[INFERRED]`; attach `CONFIDENCE: HIGH|MED|LOW|VERY LOW|UNKNOWN`.
- Do not describe zero detected glitches as proof that glitches never occur. State the observed duration and detection algorithm boundary.
- Distinguish first-to-last wall-clock span from waveform coverage. Sum each frame's `sample_count × sample_interval_s`; gaps between frames are unobserved.
- Do not call nominal comparison a traceable accuracy measurement unless calibration evidence is present.
- Do not turn RAW-buffer trigger-relative phase into absolute or connector-to-connector phase.
- If the requested conclusion needs CH2 or an independent time reference, first line: `I don't know.` Then state exactly what measurement is missing.
- If artifacts fail verification, do not interpret them as valid measurements.
- Treat user-declared physical setup separately from artifact-proven identity and settings. Label representative artifact links as representative.
