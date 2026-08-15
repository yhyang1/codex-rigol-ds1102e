---
name: rigol-acquire
description: Preflight and acquire fresh one- or two-channel waveforms from a USB-connected RIGOL DS1102E, including delayed contact, mixed pulse/static qualification, and same-trigger CH1/CH2 capture. Use for connection checks, one-shot captures, stable-contact qualification, or auditable acquisition sessions.
---

# Rigol Acquire

Use the plugin runtime, not a globally installed `rigol`. Resolve the plugin root as two directories above this `SKILL.md`, then invoke the absolute `scripts/rigol-cli` path.

## Safety and defaults

- [KNOWN] Default to CH1 only. Select `--channels 1,2` only when the user asks to use two probes.
- [KNOWN] Before USB writes, state the serial, selected channels, trigger source, profile, output directory, and command.
- [KNOWN] Run `preflight --channels ...` after declaring the intended instrument and channels. It is query-only; compare its attenuation readbacks with the physical declaration and intended profile without treating USB state as proof of wiring.
- [KNOWN] For two probes, require confirmation that each physical probe switch matches its channel's configured attenuation, both ground clips connect only to the same circuit ground potential, and the probe/scope ratings cover the signal. Stop if any answer is unknown.
- [KNOWN] Put capture output in the user's workspace or an explicitly requested directory, never inside the installed plugin.
- [KNOWN] Use a new empty output directory. If it already contains `events.jsonl`, capture directories, or reports, select a timestamped sibling; do not merge sessions.
- [KNOWN] A session temporarily changes scope settings and restores and verifies them when it exits normally, reaches a deadline, or receives SIGINT/SIGTERM.
- [COMMON] Do not change physical wiring, probe position, or external hardware.

## Select acquisition mode

Use `session` by default whenever contact is not already proven stable, the probe is hard to hold, or the user may connect it later. Use `capture` only for an explicitly requested single fresh frame with known-stable contact.

For one probe on the front-panel compensation output, use `assets/configs/probe-comp-1khz.toml`. For two 10X probes on that same safe reference point, use `assets/configs/probe-comp-two-probe-1khz.toml` only after confirming both physical switches are 10X. The two-probe profile is a configuration template, not a completed bench validation. For another source, copy the applicable TOML into the workspace and explicitly edit serial, both channel settings, trigger, timebase, and per-channel qualification limits.

Two-channel `session` requires both `[qualification.channel1]` and `[qualification.channel2]`. A frame passes only when both selected channels pass; do not weaken this to first-channel qualification. `mode = "pulse"` is the default. Use `mode = "static"` plus explicit ordered, non-overlapping `allowed_level_windows_v` for a stationary level that may validly occupy one of several states. Use `max_vpp_v` as a fail-closed noise gate; never widen it merely to promote a frame. Static qualification proves only the current level window and reports `transitions_verified: false`.

## Wait-aware session

1. Run `preflight` first and require the returned identity to be a RIGOL DS1102E matching the requested serial. Treat normalized `null` measurements as unavailable, not zero.
2. Start the session in a persistent PTY/process session. Defaults are CH1, indefinite wait (`--wait-timeout 0`), three consecutive qualified frames, and ten accepted frames. For two probes pass `--channels 1,2` and the edited two-channel profile.
3. Poll the process at intervals of at most 30 seconds. Send the user a concise status update at least every 60 seconds while it is still waiting. Do not end the turn merely because the contact is absent.
4. Treat `waiting_contact` as normal. `contact_candidate` is provisional; do not claim contact until `contact_qualified` appears.
5. The three consecutive qualifying frames are promoted and count as accepted frames; the default target is ten total, not three plus ten.
6. If the user cancels, send SIGINT first and wait for `session_cancelled` with `restored: true`. Allow up to twice the configured USB I/O timeout for an in-flight operation before diagnosing a stuck process. Do not hard-kill the process first.
7. After completion or cancellation, run `verify` on the output directory with `--output "$OUTPUT_DIR/verification.json"`. A completed collection is accepted only if verification is valid and the terminal event reports `restored: true`. A cancelled zero-capture session is valid only when its terminal restore record verifies. If `restored: false`, do not claim a safe handoff: inspect USB enumeration and setting readback, report the mismatch, and request authority before corrective writes.

Example:

```bash
"$PLUGIN_ROOT/scripts/rigol-cli" preflight --channels 1
"$PLUGIN_ROOT/scripts/rigol-cli" session \
  --config "$PLUGIN_ROOT/assets/configs/probe-comp-1khz.toml" \
  --output "$OUTPUT_DIR" --channels 1 \
  --trigger-attempt-timeout 5 --wait-timeout 0 \
  --qualify-consecutive 3 --accepted-count 10
"$PLUGIN_ROOT/scripts/rigol-cli" verify "$OUTPUT_DIR" \
  --output "$OUTPUT_DIR/verification.json"
```

For two probes, replace the profile and channel argument with:

```bash
"$PLUGIN_ROOT/scripts/rigol-cli" session \
  --config "$WORKSPACE_PROFILE" --output "$OUTPUT_DIR" \
  --channels 1,2 --trigger-attempt-timeout 5 \
  --wait-timeout 0 --qualify-consecutive 3 --accepted-count 10
```

Report the artifact path, selected channels, each channel's qualification mode and matched static window when applicable, contact epochs, accepted/rejected/waiting counts, restore status, and verification result. State `transitions_verified: false` for static frames. Describe dual data as "simultaneously sampled, sequentially downloaded." Tag measured values `[COMPUTED]` and instrument identity or saved metadata `[KNOWN]`; include a confidence label.
