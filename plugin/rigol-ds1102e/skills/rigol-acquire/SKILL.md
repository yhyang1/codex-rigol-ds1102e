---
name: rigol-acquire
description: Acquire fresh CH1 waveforms from a USB-connected RIGOL DS1102E, including waiting for delayed, difficult, or intermittent probe contact. Use for scope connection checks, one-shot captures, stable-contact qualification, or collecting an auditable capture session.
---

# Rigol Acquire

Use the plugin runtime, not a globally installed `rigol`. Resolve the plugin root as two directories above this `SKILL.md`, then invoke the absolute `scripts/rigol-cli` path.

## Safety and defaults

- [KNOWN] Default to CH1 only. Do not enable or acquire CH2 unless the user explicitly asks.
- [KNOWN] State the intended instrument serial, profile, output directory, and command before sending USB configuration writes.
- [KNOWN] Put capture output in the user's workspace or an explicitly requested directory, never inside the installed plugin.
- [KNOWN] Use a new empty output directory. If it already contains `events.jsonl`, capture directories, or reports, select a timestamped sibling; do not merge sessions.
- [KNOWN] A session temporarily changes scope settings and restores and verifies them when it exits normally, reaches a deadline, or receives SIGINT/SIGTERM.
- [COMMON] Do not change physical wiring, probe position, or external hardware.

## Select acquisition mode

Use `session` by default whenever contact is not already proven stable, the probe is hard to hold, or the user may connect it later. Use `capture` only for an explicitly requested single fresh frame with known-stable contact.

For the front-panel probe compensation output, use `assets/configs/probe-comp-1khz.toml` from the plugin root. Its `probe = 1` value is the oscilloscope CH1 attenuation-menu setting; verify the saved readback. For another source, copy the TOML into the workspace and explicitly edit the instrument serial, CH1 attenuation/scale, trigger, timebase, nominal frequency, Vpp bounds, complete-pulse minimum, and period-CV limit before acquisition.

## Wait-aware session

1. Run `doctor` first and require the returned identity to be a RIGOL DS1102E matching the requested serial.
2. Start the session in a persistent PTY/process session. Default arguments are CH1, indefinite wait (`--wait-timeout 0`), three consecutive qualified frames, and ten accepted frames.
3. Poll the process at intervals of at most 30 seconds. Send the user a concise status update at least every 60 seconds while it is still waiting. Do not end the turn merely because the contact is absent.
4. Treat `waiting_contact` as normal. `contact_candidate` is provisional; do not claim contact until `contact_qualified` appears.
5. The three consecutive qualifying frames are promoted and count as accepted frames; the default target is ten total, not three plus ten.
6. If the user cancels, send SIGINT first and wait for `session_cancelled` with `restored: true`. Allow up to twice the configured USB I/O timeout for an in-flight operation before diagnosing a stuck process. Do not hard-kill the process first.
7. After completion or cancellation, run `verify` on the output directory with `--output "$OUTPUT_DIR/verification.json"`. A completed collection is accepted only if verification is valid and the terminal event reports `restored: true`. A cancelled zero-capture session is valid only when its terminal restore record verifies. If `restored: false`, do not claim a safe handoff: inspect USB enumeration and setting readback, report the mismatch, and request authority before corrective writes.

Example:

```bash
"$PLUGIN_ROOT/scripts/rigol-cli" doctor
"$PLUGIN_ROOT/scripts/rigol-cli" session \
  --config "$PLUGIN_ROOT/assets/configs/probe-comp-1khz.toml" \
  --output "$OUTPUT_DIR" --channels 1 \
  --trigger-attempt-timeout 5 --wait-timeout 0 \
  --qualify-consecutive 3 --accepted-count 10
"$PLUGIN_ROOT/scripts/rigol-cli" verify "$OUTPUT_DIR" \
  --output "$OUTPUT_DIR/verification.json"
```

Report the artifact path, contact epoch count, accepted/rejected/waiting counts, restore status, and verification result. Tag measured values `[COMPUTED]` and instrument identity or saved metadata `[KNOWN]`; include a confidence label.
