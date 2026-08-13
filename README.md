# rigol-tool

USB automation and auditable waveform capture for the RIGOL DS1102E.

```bash
uv sync
uv run rigol doctor
uv run rigol capture --output captures --trigger-timeout 10
uv run rigol watch --output captures --interval 60 --trigger-timeout 10 --count 10
uv run rigol session --config configs/probe-comp-1khz.toml --output captures/session --channels 1
uv run rigol verify captures/session --output captures/session/verification.json
uv run rigol export-csv captures/20260809T120000.000000Z_000001
uv run rigol analyze captures/20260809T120000.000000Z_000001 --nominal-frequency 1000
uv run rigol analyze-series captures/watch-10 --nominal-frequency 1000
uv run rigol analyze-paired-series captures/session \
  --trigger-channel 1 --strobe-channel 2 --expectations expectations.json
```

Use `--config config.toml` to apply an explicit acquisition profile. Without a
profile, channel, timebase, and trigger parameters are preserved; the waveform
point mode, trigger sweep, and run state are temporarily changed and restored.

The DS1102E must be observed in an armed state before `STOP` is accepted as a
fresh trigger. A trigger timeout is an error, and every changed setting is
restored and verified. Firmware 00.04.02 requires setter-specific SCPI
normalization (`CH1` -> `CHAN1`, trigger `NORMAL` -> `NORM`, and decimal numeric
write-back), which this tool handles.

For one-channel self-triggered measurements, frequency, period jitter,
missing/extra pulses, pulse width, and amplitude outliers are supported.
Absolute long-term phase and connector end-to-end phase are not measurable
without a second independent timing reference. The reported RAW-buffer phase is
diagnostic only. Frequency accuracy is relative to the oscilloscope sampling
timebase unless that timebase has been externally calibrated.

Synchronized two-channel captures can also be checked as a causal pulse pair.
`analyze-paired-series` verifies the capture hashes first, detects hysteretic
edges on both channels, pairs dependent pulses only inside complete consecutive
trigger intervals, and reports trigger period/high width, trigger-to-dependent
delay, dependent width, logic levels, and missing or extra pulses. Optional
JSON expectations provide nominal timing and logic-level gates; the result is
written atomically as `paired-series-analysis.json`.

Example profile:

```toml
[instrument]
serial = "DS1ET183009083"

[acquisition]
memory_depth = "NORMAL"
type = "NORMAL"

[channel1]
display = true
coupling = "DC"
probe = 1
scale_v_div = 1.0
offset_v = 0.0
bandwidth_limit = false

[trigger]
mode = "EDGE"
source = "CHAN1"
slope = "POSITIVE"
level_v = 1.5
coupling = "DC"

[timebase]
scale_s_div = 0.0005
offset_s = 0.0
```

The checked-in front-panel probe-compensation profile is
`configs/probe-comp-1khz.toml`. Its wait-aware default uses NORMAL memory and
0.5 ms/div so contact qualification does not depend on the maximum-depth USB
transfer. The observed DS1102E return size for this profile is 16,384 points;
the saved metadata remains authoritative. Use a separate LONG-memory profile
only when the bench USB path has already passed deep-buffer transfer validation.

## Wait-aware acquisition

`session` keeps one USB connection and acquisition configuration active while
waiting for a trigger. By default it waits indefinitely, requires three
consecutive qualified CH1 frames before declaring contact, and retains ten
qualified frames. A timeout or rejected candidate does not end the process.
SIGINT/SIGTERM requests an orderly stop so the original oscilloscope settings
can be restored and verified.

The profile's `[qualification]` section sets nominal frequency, allowed
frequency and Vpp ranges, minimum complete pulses, and period-CV limit. Use
`--wait-timeout SECONDS` only when a finite unattended deadline is intended.

## Codex plugin

[KNOWN] `rigol-tool` 同时提供普通 Python CLI 和 Codex plugin。Python CLI 负责
USB/SCPI、采集、制品校验与数值分析；plugin 负责把这些能力、等待策略和证据边界交给
Codex。它不是常驻后台服务，也不是通用示波器平台。

### Repository layout

```text
src/rigol_tool/                         Python runtime and CLI
configs/                                Editable acquisition profiles
plugin/rigol-ds1102e/
├── .codex-plugin/plugin.json           Plugin manifest
├── scripts/rigol-cli                   Plugin runtime entrypoint
├── assets/configs/                     Profile bundled with the plugin
└── skills/
    ├── rigol-acquire/                  Wait and acquire
    ├── rigol-analyze/                  Verify and analyze artifacts
    ├── rigol-interpret/                Produce interpretation.md
    └── rigol-run-workflow/             End-to-end orchestration
scripts/package_codex_plugin.py         Build an installable plugin directory
```

[KNOWN] `plugin/rigol-ds1102e` and `src/rigol_tool` are the canonical editable
sources. `build/codex-plugin/rigol-ds1102e`, `~/plugins/rigol-ds1102e`, and
`~/.codex/plugins/cache/...` are generated or installed copies; do not make the
only copy of a change there.

### Included Skills

| Skill | Use | USB access | Output |
|---|---|---:|---|
| `rigol-acquire` | [KNOWN] Identify the instrument, wait for delayed or intermittent CH1 contact, require three consecutive qualified frames, and retain ten total frames. | Yes | Capture directory, `events.jsonl`, `verification.json` |
| `rigol-analyze` | [KNOWN] Verify saved hashes and calculate frequency, timing, pulse-width, missing/extra-pulse, amplitude-outlier, and RAW-buffer-relative phase statistics. | No | `series-analysis.json` |
| `rigol-interpret` | [KNOWN] Convert verified analysis into evidence-bounded conclusions while preserving CH1-only, calibration, phase, and observation-gap limitations. | No | `interpretation.md` and a chat summary |
| `rigol-run-workflow` | [KNOWN] Run doctor → wait/acquire → verify → analyze → interpret without skipping failed gates. | Yes, during acquisition | Complete acquisition and report directory |

[KNOWN] The first three qualifying frames are provisional until the third
passes; once contact is established, those three frames are promoted and count
toward the ten-frame default target.

[KNOWN] `waiting_contact` is a normal nonterminal state. Codex keeps the command
alive in a persistent process, polls it, and can wait indefinitely for the user
to touch or attach the probe. USB loss is handled by an outer reconnect loop;
probe qualification restarts after transport loss.

### Build the plugin

[KNOWN] The following commands create a plugin directory with a locked `uv`
runtime and a synchronized plugin-local virtual environment:

```bash
uv sync
uv run pytest
uv run python scripts/package_codex_plugin.py
build/codex-plugin/rigol-ds1102e/scripts/rigol-cli --help
```

[KNOWN] The built plugin is written to
`build/codex-plugin/rigol-ds1102e`. Its bundled default profile is CH1-only,
1×, nominal 1 kHz, NORMAL memory, and 0.5 ms/div.

### First installation into Codex

[KNOWN] This project uses Codex's default personal marketplace. The marketplace
file is `~/.agents/plugins/marketplace.json`, and its plugin source is
`~/plugins/rigol-ds1102e`.

[KNOWN] Run the scaffold command only once, when the personal marketplace entry
and `~/plugins/rigol-ds1102e` do not yet exist:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/create_basic_plugin.py \
  rigol-ds1102e \
  --with-skills --with-scripts --with-assets \
  --with-marketplace \
  --category "Developer Tools"
```

[KNOWN] Then copy the verified build into the personal plugin source and ask
Codex to install it from the implicitly discovered `personal` marketplace:

```bash
/usr/bin/ditto \
  build/codex-plugin/rigol-ds1102e \
  ~/plugins/rigol-ds1102e

codex plugin add rigol-ds1102e@personal
codex plugin list --marketplace personal
```

[KNOWN] Do not run `codex plugin marketplace add` for this default personal
marketplace path. That command is for non-default marketplace roots.

[KNOWN] Installation is accepted only when `codex plugin list` shows
`rigol-ds1102e@personal` as `installed, enabled` and the expected version.
Start a new Codex thread after installation so the newly installed Skills are
loaded into that thread.

### Updating an existing installation

[KNOWN] Codex caches plugins by version. After changing `src/`, the plugin
manifest, bundled assets, or any `SKILL.md`, replace the cachebuster, rebuild,
copy, and reinstall:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py \
  plugin/rigol-ds1102e

uv run python scripts/package_codex_plugin.py

/usr/bin/ditto \
  build/codex-plugin/rigol-ds1102e \
  ~/plugins/rigol-ds1102e

codex plugin add rigol-ds1102e@personal
codex plugin list --marketplace personal
```

[KNOWN] The cachebuster helper replaces the existing `+codex.<token>` suffix;
it does not append multiple suffixes. Start another new Codex thread after
reinstallation.

### Using the plugin in Codex

[KNOWN] Codex may select a Skill from its description, or the user can request
one explicitly. Example prompts:

```text
Use $rigol-run-workflow to wait for CH1 contact, retain ten qualified
front-panel test-output captures, analyze them, and write interpretation.md.

Use $rigol-acquire to arm the DS1102E now and keep waiting while I attach the
probe. Use CH1 only.

Use $rigol-analyze to verify and analyze captures/session at nominal 1000 Hz.

Use $rigol-interpret to explain captures/session/series-analysis.json without
claiming absolute phase or calibrated frequency accuracy.
```

[KNOWN] Before USB configuration writes, the acquisition Skill declares the
instrument serial, profile, output directory, and command. Codex may request
sandbox approval for USB access. Review those targets before approving.

[KNOWN] To cancel a waiting acquisition, tell Codex to cancel or send SIGINT in
a manual terminal. The workflow waits for `session_cancelled` and
`restored: true`, then verifies the partial run. A run with `restored: false`
is not a safe completed handoff.

### Optional validation before installation

[KNOWN] The plugin and each Skill can be checked with Codex's bundled
validators before copying them into `~/plugins`:

```bash
uv run --with pyyaml python \
  ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py \
  build/codex-plugin/rigol-ds1102e

for skill in plugin/rigol-ds1102e/skills/*; do
  uv run --with pyyaml python \
    ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$skill"
done
```
