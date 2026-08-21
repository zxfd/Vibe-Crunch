# Vibe Crunch 🏋️

> **When AI is crunching code, you should be crunching too.**
>
> 当 AI 在卷代码的时候，你也该卷腹了。

[简体中文](README.zh-CN.md) | **English**

Vibe Crunch turns AI coding wait time into **2–4 minute micro-workouts**. When a task is submitted in Codex / Claude Code, the AI starts immediately and Vibe Crunch independently decides whether to show a short exercise reminder.

The primary target is **ChatGPT / Codex Desktop on macOS**. **Codex CLI is not required** for the normal desktop workflow.

Current plugin version: **v2.0.3**.

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
      rotate exercise
              │
              ├────────────────────────► AI keeps working
              │
              ▼
      Vibe Crunch dialog
      2–4 minute micro-workout
      [完成了] [跳过这次] [今天休息]
```

The hook is **fail-open**: reminder failures must not block the AI task.

## Defaults

- 30-minute cooldown between automatic reminders
- **5 completed micro-workouts per day** as the default goal
- **Skip does not consume the daily goal**; another reminder may appear after the cooldown
- **Rest today** suppresses later automatic reminders for the local day
- one pending reminder across concurrent sessions
- pending reminders expire after 90 minutes
- deterministic exercise rotation
- roughly 2–4 reps in reserve per set
- no webcam, OpenCV, MediaPipe, or pose model in the default mode
- Chinese-first macOS dialog

The daily goal is completion-based rather than reminder-based. Manual `vibe-crunch now` workouts count when completed, because they still contribute to actual training volume.

| Order | Exercise | Dose |
|---|---|---|
| A | Push-ups | 2 × 8–12 |
| B | Band / backpack rows | 2 × 12–15 |
| C | Chair squats | 2 × 10–15 |
| D | Glute bridges | 2 × 12–20 |
| E | Dead bug | 2 × 8–10 / side |

This is an **exercise snack**, not a complete workout session.

## Chinese macOS dialog

The dialog shows the exercise, sets, reps, a short technique cue, and the meaning of each button:

- **完成了** — record this micro-workout as completed
- **跳过这次** — skip only the current reminder; later reminders remain eligible after cooldown
- **今天休息** — suppress automatic reminders for the rest of the local day

Internal exercise keys remain stable so persisted state and statistics stay compatible.

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
2. `~/.local/bin/vibe-crunch now` opens a Chinese dialog.
3. Clicking **完成了** increments today's completion count.
4. Clicking **跳过这次** leaves today's completion count unchanged.
5. A normal Codex task starts immediately while the workout dialog is open.
6. Repeated manual `now` runs rotate exercises.
7. **今天休息** suppresses later automatic reminders for that day; manual `now` remains available.
8. Default settings report a 30-minute cooldown and a daily completion goal of 5.

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
```

This keeps micro-workout scheduling and statistics isolated from the retained upstream webcam mode.

## Scheduling rationale

A coding session can contain many tiny prompts. Triggering a workout on every prompt creates notification fatigue, so the hook is only an event source; a state machine decides whether an automatic reminder is useful.

The scheduler enforces cooldown, a completion-based daily goal, a single pending reminder, exercise rotation, rest-of-day suppression, and duplicate-hook suppression.

## Legacy webcam mode

The upstream Workout Gate webcam implementation remains available for compatibility. It is not part of the default Vibe Crunch flow.

To use it explicitly from a source checkout:

```sh
./bootstrap.sh
```

That path installs OpenCV, MediaPipe, and the pose model.

## Development

Focused scheduler tests:

```sh
python3 -m unittest tests.test_micro_plan
```

Project layout:

```text
hooks/micro_gate.py           non-blocking UserPromptSubmit hook
workout_gate/micro_plan.py    cooldown / completion goal / rotation policy
workout_gate/micro.py         state, stats, Chinese dialogs and control CLI
hooks/gate.sh                 Codex / Claude hook entry
hooks/session_start.sh        lightweight plugin initialization
vibe-crunch                   source-checkout launcher
```

## License and upstream

MIT. Vibe Crunch retains the original Workout Gate code and license. Credit for the upstream webcam challenge architecture and implementation belongs to [BotchetDig/workout-gate](https://github.com/BotchetDig/workout-gate).
