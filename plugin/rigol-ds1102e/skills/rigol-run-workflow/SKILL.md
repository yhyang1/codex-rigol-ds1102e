---
name: rigol-run-workflow
description: Run the complete RIGOL DS1102E CH1 workflow from USB identity and wait-aware contact acquisition through artifact verification, pulse analysis, and interpretation.md. Use for end-to-end bench measurements when the probe may be connected later or is difficult to hold.
---

# Rigol Run Workflow

Run the four gates in order. Do not skip a failed gate.

## Gate 1: identify and declare

Resolve the plugin root as two directories above this `SKILL.md`. Declare the serial, CH1-only profile, nominal frequency, qualification bounds, output directory, three-frame contact requirement, ten-frame target, and indefinite-wait behavior. Run the plugin's absolute `scripts/rigol-cli doctor` path and confirm identity.

## Gate 2: wait and acquire

Follow `rigol-acquire`. Default to `assets/configs/probe-comp-1khz.toml`, CH1, `--wait-timeout 0`, `--qualify-consecutive 3`, and `--accepted-count 10`. Keep the process alive when there is no trigger. Poll at most every 30 seconds and update the user at least every 60 seconds. On cancellation, use SIGINT and wait for restoration evidence.

## Gate 3: verify and analyze

Run `verify` on the run. Continue only if it reports valid artifacts, one terminal session event, matching accepted/capture counts, and `restored: true`. Then follow `rigol-analyze` with the declared nominal frequency and CH1.

## Gate 4: interpret

Follow `rigol-interpret`. Write a non-overwriting `interpretation.md` report beside the run and provide the same concise evidence-bounded result in chat.

## Failure behavior

- [KNOWN] `waiting_contact` and `contact_candidate` are nonterminal states; remain active.
- [KNOWN] `candidate_rejected` and `contact_lost` reset the consecutive-frame gate; do not promote provisional frames.
- [KNOWN] A complete acquisition requires ten accepted artifacts plus a verified terminal restore record.
- [INFERRED] If contact repeatedly drops, report the observed qualification failures without diagnosing the physical cause unless evidence identifies it.
- [COMMON] Never alter the user's physical connections or energize a different source.

The final result must include exact artifact/report paths, capture and wait counts, computed findings, limitations, confidence, and `[RULES I BROKE]`.
