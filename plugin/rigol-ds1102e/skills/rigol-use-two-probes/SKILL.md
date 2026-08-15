---
name: rigol-use-two-probes
description: Safely run a same-trigger two-probe workflow on a USB-connected RIGOL DS1102E, including read-only preflight, grounding and attenuation confirmation, mixed pulse/static CH1/CH2 qualification, artifact verification, analysis, and evidence-bounded interpretation. Use when the user mentions two probes, both channels, CH1 and CH2, static logic levels, or channel-to-channel delay.
---

# Rigol Use Two Probes

Resolve the plugin root as two directories above this `SKILL.md` and invoke its absolute `scripts/rigol-cli` path.

## Gate 1: declare and read-only preflight

State the instrument serial, CH1/CH2 roles and signal classes, trigger source, workspace profile, output directory, and exact acquisition command. Run `preflight --channels 1,2`; this is query-only. Require exact DS1102E identity and compare current attenuation readbacks with the intended profile.

Before any USB configuration write, require the user to confirm all three physical items:

1. Each physical probe switch matches its channel's configured attenuation.
2. Both probe ground clips connect only to the same circuit ground potential.
3. The expected signal is within both probe and oscilloscope voltage/category ratings.

If any item is unknown, stop before USB writes. Do not move probes, change wiring, or energize the DUT.

## Gate 2: profile and identity

Copy `assets/configs/probe-comp-two-probe-1khz.toml` into the workspace only for two 10X probes measuring the same front-panel compensation reference. Otherwise create a workspace profile with `[channel1]`, `[channel2]`, and independent `[qualification.channel1]` and `[qualification.channel2]` sections. Never edit the installed asset.

For every channel set `mode = "pulse"` or `mode = "static"` explicitly in the workspace profile when the signals differ. Static mode requires user-declared `allowed_level_windows_v`; use `max_vpp_v` as the noise gate. Do not add DUT-specific defaults to the installed plugin.

## Gate 3: acquire both channels

Run `session --channels 1,2` in a persistent process. Use NORMAL memory unless this exact two-channel USB path has separately passed LONG transfer validation. Keep waiting through `waiting_contact`; require three consecutive frames in which every pulse/static channel passes, and retain ten total accepted frames by default. Do not weaken static voltage/noise gates to force promotion.

```bash
"$PLUGIN_ROOT/scripts/rigol-cli" session \
  --config "$WORKSPACE_PROFILE" --output "$OUTPUT_DIR" \
  --channels 1,2 --trigger-attempt-timeout 5 \
  --wait-timeout 0 --qualify-consecutive 3 --accepted-count 10
```

On cancellation, send SIGINT and wait for `restored: true`. On transport loss, let the outer reconnect loop re-identify the instrument and restart shared contact qualification.

## Gate 4: verify and analyze

Run `verify` first. Continue only if every accepted capture contains both channels, the hashes and array lengths are valid, session counts agree, and restoration is true.

For independent pulse signals, run `analyze-series` once per requested pulse channel. For static channels, report saved qualification metrics, matched window, noise gate, and `transitions_verified: false`; do not run pulse analysis. For causal pulse timing, run `analyze-paired-series` with distinct trigger/dependent channels and an expectations JSON when pass/fail is requested.

## Gate 5: interpret

Follow `rigol-interpret`. State that channels were simultaneously sampled and sequentially downloaded. Treat sample timing as relative to the oscilloscope timebase unless calibration evidence exists. Treat the manual's typical 500 ps inter-channel delay as a specification, not an automatic correction or a measured result.

Report exact artifact paths, serial, selected channels, per-channel qualification counts, sample interval and point count, restoration, verification, analysis gate, limitations, confidence, and `[RULES I BROKE]`.
