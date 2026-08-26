# Vibe Crunch 🏋️

> **When AI is crunching code, you should be crunching too.**
>
> 当 AI 在卷代码的时候，你也该卷腹了。

[简体中文](README.zh-CN.md) | **English**

Vibe Crunch breaks long AI-assisted coding sessions into **roughly 30-second to 3-minute movement snacks**. When you submit a task in Codex / Claude Code, the AI starts immediately while Vibe Crunch independently decides whether to show a short exercise reminder.

The primary target is **ChatGPT / Codex Desktop on macOS**. The normal desktop workflow requires **neither Codex CLI nor a webcam**.

## Behavior

```text
Submit an AI task
      │
      ▼
UserPromptSubmit
      │
      ├── cooldown satisfied?
      ├── today's completion goal not reached?
      ├── no pending reminder?
      └── not resting today?
              │
              ▼
      randomly draw 1 exercise from the pool
              │
              ├────────────────────────► AI keeps working
              │
              ▼
      Vibe Crunch dialog
      ~30 seconds to 3 minutes
      [完成了] [换一个] [跳过这次] [今天休息]
```

The hook is **fail-open**: reminder failures must never block the AI task. Successful `UserPromptSubmit` hooks keep stdout and stderr empty so Vibe Crunch does not inject incidental text into Codex model context.

Vibe Crunch **does not use webcam recognition, pose landmarks, or automatic rep validation**. Completion is self-reported: the workout is counted only after the user clicks **完成了**.

## Defaults

- 30-minute cooldown between automatic reminders
- **5 completed micro-workouts per day** as the default goal
- each new reminder is drawn **uniformly at random** from the current exercise pool
- there is no rotation order and no anti-repeat rule, so consecutive reminders may randomly choose the same exercise
- **Swap** redraws randomly from the pool excluding the current exercise, without counting as a skip, completion, new reminder, or cooldown event
- **Skip does not consume the daily goal**; another reminder may appear after the cooldown
- **Rest today** suppresses later automatic reminders for the local day
- one pending reminder across concurrent sessions
- pending reminders expire after 90 minutes
- no webcam, OpenCV, MediaPipe, or pose model in the default Vibe Crunch flow
- Chinese-first macOS dialog

The daily goal is completion-based rather than reminder-based. Manual `vibe-crunch now` workouts count when completed because they still contribute to actual activity.

## Current default exercise pool

The current pool is biased toward **sedentary desk work, relatively low recent activity, rebuilding baseline strength, and conservative knee loading**. Dynamic squats, lunges, jumping and other higher-impact or more technique-sensitive lower-body movements are not part of the default random pool.

| Exercise | Default dose | Main purpose |
|---|---|---|
| Push-ups | 1 × 4–6 | Upper-body pushing without going to failure |
| Wall sit | 1 × 20–30 sec | Conservative lower-body isometric work at a comfortable shallow-to-moderate knee angle |
| Plank | 1 × 30–40 sec | Core anti-extension |
| Glute bridges | 1 × 12–15 | Glutes / posterior chain after prolonged sitting |
| Side-lying leg raises | 1 × 10–15 / side | Lateral hip stability with almost no knee flexion-extension |
| Dead bug | 1 × 6–8 / side | Core control |
| Bird dog | 1 × 6–8 / side | Trunk stability and low-back control |
| Standing calf raises | 1 × 15–20 | Lower-leg movement and brief time away from the chair |
| Walk around | 2–3 min | Directly break up prolonged sitting |
| Wall angels | 1 × 8–12 | Thoracic / scapular movement after desk posture |

This is an **exercise snack**, not a complete training session and not a substitute for a structured strength or rehabilitation program.

The wall-sit cue explicitly says **not to chase a 90-degree knee angle and to stop if the knee becomes painful, catches, or feels clearly abnormal**. The goal here is gradual exposure, not testing knee limits.

## Optional Apple Health sync

A completed Vibe Crunch session can optionally be logged into Apple Health as an iPhone HealthKit Workout. The feature is off by default because it requires one-time Apple Shortcuts / Focus setup.

The Mac cannot directly access the Apple Health database, so the zero-server bridge is:

```text
Vibe Crunch completion
→ iCloud event ledger
→ Mac Shortcut
→ shared Focus signal
→ iPhone personal automation
→ Log Workout
→ Apple Health
```

The first version never guesses calories, heart rate, or distance. It only records a native workout category and conservative duration. The exact Vibe Crunch exercise, target, completion timestamp, and event ID remain in the iCloud JSON ledger for debugging, backfill, or a future native iPhone companion.

See [`docs/apple-health-sync.md`](docs/apple-health-sync.md) for the one-time setup and acceptance test.

After setup:

```sh
vibe-crunch health-sync status
vibe-crunch health-sync on
```

Disable it at any time with:

```sh
vibe-crunch health-sync off
```

## Chinese macOS dialog

The dialog shows the exercise, dose, a short technique cue, and four controls:

- **完成了** — record this micro-workout as completed; if Apple Health sync is enabled, also emit a sync event
- **换一个** — immediately redraw another random exercise while keeping the same reminder open
- **跳过这次** — skip only the current reminder; later reminders remain eligible after cooldown
- **今天休息** — suppress automatic reminders for the rest of the local day

A native `NSAlert` is retained as the macOS fallback UI; the lightweight project UI is preferred when available.

## Codex Desktop installation

Use the **Plugins UI inside ChatGPT / Codex Desktop**. Installing the `codex` terminal command is not required.

Plugin name:

```text
vibe-crunch
```

Repository:

```text
https://github.com/zxfd/Vibe-Crunch
```

After installing or updating:

1. approve the `UserPromptSubmit` hook if Codex asks for trust;
2. completely quit and reopen ChatGPT / Codex Desktop;
3. start a new Codex session;
4. verify the helper from Terminal.

`SessionStart` installs the helper at:

```text
~/.local/bin/vibe-crunch
```

## Commands

These are ordinary shell commands, not Codex CLI commands.

```sh
~/.local/bin/vibe-crunch status
~/.local/bin/vibe-crunch on
~/.local/bin/vibe-crunch off
~/.local/bin/vibe-crunch now
~/.local/bin/vibe-crunch done
~/.local/bin/vibe-crunch skip
~/.local/bin/vibe-crunch rest

~/.local/bin/vibe-crunch set cooldown 30
~/.local/bin/vibe-crunch set daily-goal 5

~/.local/bin/vibe-crunch health-sync status
~/.local/bin/vibe-crunch health-sync on
~/.local/bin/vibe-crunch health-sync off
~/.local/bin/vibe-crunch health-sync trigger
```

If `~/.local/bin` is already on `PATH`:

```sh
vibe-crunch status
vibe-crunch now
```

From a source checkout:

```sh
./vibe-crunch status
./vibe-crunch now
```

To disable automatic reminders immediately:

```sh
~/.local/bin/vibe-crunch off
```

Re-enable them with:

```sh
~/.local/bin/vibe-crunch on
```

## Acceptance test

Seeing the dialog already proves the core hook chain is alive:

```text
Codex Desktop
→ UserPromptSubmit
→ hooks/gate.sh
→ hooks/micro_gate.py
→ detached Vibe Crunch UI
```

For full acceptance:

1. `~/.local/bin/vibe-crunch status` succeeds.
2. Run `~/.local/bin/vibe-crunch now` several times; exercises come from the default pool without a deterministic rotation order.
3. `~/.local/bin/vibe-crunch now` opens a Chinese dialog with four controls.
4. Clicking **完成了** increments today's completion count.
5. Clicking **换一个** immediately redraws another exercise without changing today's completion count or creating another automatic reminder.
6. Clicking **跳过这次** leaves today's completion count unchanged.
7. A normal Codex task starts immediately while the workout dialog is open.
8. **今天休息** suppresses later automatic reminders for that day; manual `now` remains available.
9. Default settings report a 30-minute cooldown and a daily completion goal of 5.
10. The normal Vibe Crunch flow never requests camera permission.
11. If Apple Health sync is enabled, only **完成了** emits a Health event; swap / skip / rest never write a workout.

## State and statistics

Runtime data lives under:

```text
~/.workout-gate/
```

Vibe Crunch uses separate files:

```text
vibe-crunch.json
vibe-crunch-state.json
vibe-crunch-stats.json
vibe-crunch-health-sync.json
```

The Apple Health event ledger defaults to:

```text
~/Library/Mobile Documents/com~apple~CloudDocs/VibeCrunch/HealthSync/events/
```

The active pool is configured with `exercise_pool`. Legacy rotation state is ignored by the new random scheduler.

## Scheduling rationale

A coding session can contain many tiny prompts. Triggering a workout on every prompt creates notification fatigue, so the hook is only an event source; a state machine decides whether an automatic reminder is useful.

The scheduler enforces cooldown, a completion-based daily goal, a single pending reminder, fully random exercise selection, rest-of-day suppression, and duplicate-hook suppression. Swapping mutates the current pending reminder instead of creating another reminder, so it does not distort cooldown or daily scheduling counters.

## About the webcam code still in the repository

The repository historically descends from Workout Gate, so upstream compatibility files such as `challenge.py` and `detector.py` are still present.

**They are not part of the current default Vibe Crunch path and are not called by the normal `hooks/micro_gate.py` workflow.** Vibe Crunch itself does not depend on camera recognition. Those files remain only for upstream compatibility and source-history traceability.

## Development

Focused tests:

```sh
python3 -m unittest tests.test_health_sync
python3 -m unittest tests.test_micro_plan
python3 -m unittest tests.test_micro_config
python3 -m unittest tests.test_micro_gate
python3 -m unittest tests.test_micro_ui
```

`.github/workflows/micro-tests.yml` runs the same camera-free suite for the feature branch and pull requests.

Project layout:

```text
hooks/micro_gate.py           non-blocking UserPromptSubmit hook
workout_gate/micro_plan.py    cooldown / completion goal / random exercise pool
workout_gate/micro.py         state, stats, Chinese dialogs and control CLI
workout_gate/health_sync.py   Mac → Focus → iPhone HealthKit bridge
hooks/gate.sh                 Codex / Claude hook entry
hooks/session_start.sh        lightweight plugin initialization
vibe-crunch                   source-checkout launcher
```

## License and upstream

MIT. Vibe Crunch retains the original Workout Gate code and license. Credit for the historical upstream architecture and implementation belongs to [BotchetDig/workout-gate](https://github.com/BotchetDig/workout-gate).
