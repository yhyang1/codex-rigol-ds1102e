---
name: rigol-use-two-probes
description: Safely run a same-trigger two-probe workflow on a USB-connected RIGOL DS1102E, including grounding and attenuation confirmation, independent CH1/CH2 contact qualification, artifact verification, per-channel or paired timing analysis, and evidence-bounded interpretation. Use when the user mentions two probes, both channels, CH1 and CH2, or channel-to-channel delay.
---

# Rigol Use Two Probes

Resolve the plugin root as two directories above this `SKILL.md` and invoke its absolute `scripts/rigol-cli` path.

## Gate 1: physical safety and declaration

Before any USB configuration write, state the instrument serial, CH1/CH2 roles, trigger source, workspace profile, output directory, and exact command. Require the user to confirm all three items:

1. Each physical probe switch matches its channel's configured attenuation.
2. Both probe ground clips connect only to the same circuit ground potential.
3. The expected signal is within both probe and oscilloscope voltage/category ratings.

If any item is unknown, stop before USB writes. Do not move probes, change wiring, or energize the DUT.

## Gate 2: profile and identity

Copy `assets/configs/probe-comp-two-probe-1khz.toml` into the workspace only for two 10X probes measuring the same front-panel compensation reference. Otherwise create a workspace profile with `[channel1]`, `[channel2]`, and independent `[qualification.channel1]` and `[qualification.channel2]` sections. Never edit the installed asset.

Run `doctor` and require an exact RIGOL DS1102E identity matching the declared serial.

## Gate 3: acquire both channels

Run `session --channels 1,2` in a persistent process. Use NORMAL memory unless this exact two-channel USB path has separately passed LONG transfer validation. Keep waiting through `waiting_contact`; require three consecutive frames in which both channels pass, and retain ten total accepted frames by default.

```bash
"$PLUGIN_ROOT/scripts/rigol-cli" session \
  --config "$WORKSPACE_PROFILE" --output "$OUTPUT_DIR" \
  --channels 1,2 --trigger-attempt-timeout 5 \
  --wait-timeout 0 --qualify-consecutive 3 --accepted-count 10
```

On cancellation, send SIGINT and wait for `restored: true`. On transport loss, let the outer reconnect loop re-identify the instrument and restart shared contact qualification.

## Gate 4: verify and analyze

Run `verify` first. Continue only if every accepted capture contains both channels, the hashes and array lengths are valid, session counts agree, and restoration is true.

For independent signals, run `analyze-series` once per requested channel. For causal timing, run `analyze-paired-series` with distinct trigger/dependent channels and an expectations JSON when pass/fail is requested.

## Gate 5: interpret

Follow `rigol-interpret`. State that channels were simultaneously sampled and sequentially downloaded. Treat sample timing as relative to the oscilloscope timebase unless calibration evidence exists. Treat the manual's typical 500 ps inter-channel delay as a specification, not an automatic correction or a measured result.

Report exact artifact paths, serial, selected channels, per-channel qualification counts, sample interval and point count, restoration, verification, analysis gate, limitations, confidence, and `[RULES I BROKE]`.
