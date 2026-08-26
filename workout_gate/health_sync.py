"""Bridge completed Vibe Crunch sessions from macOS to iPhone HealthKit.

macOS cannot read/write HealthKit. The zero-server MVP therefore uses iCloud
Drive as a durable outbox and a tiny macOS Shortcut as a cross-device signal:

    Vibe Crunch done
      -> write one JSON event into iCloud Drive
      -> run macOS Shortcut "Vibe Crunch Health Sync"
      -> that Shortcut enables a shared Focus
      -> iPhone personal automation wakes, reads the outbox, logs workouts,
         moves processed files away, and disables the Focus again

The bridge is disabled by default so existing installs keep working until the
one-time iPhone/macOS Shortcuts setup is complete. A failed trigger never loses
an event: it remains in the outbox and the next successful trigger can flush it.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import store

CONFIG_NAME = "vibe-crunch-health-sync.json"
DEFAULT_SHORTCUT = "Vibe Crunch Health Sync"
DEFAULT_CONFIG = {
    "enabled": False,
    "transport": "icloud-focus-shortcuts",
    "trigger_shortcut": DEFAULT_SHORTCUT,
}

# Apple Health workout categories. We deliberately do NOT fabricate calories,
# heart rate, or distance. Duration is a conservative estimate based on how
# long the reminder was open, clamped to a plausible range for each exercise.
EXERCISE_HEALTH_PROFILE = {
    "pushups": ("functional_strength_training", "Functional Strength Training", 15, 60),
    "wall_sit": ("functional_strength_training", "Functional Strength Training", 20, 45),
    "plank": ("core_training", "Core Training", 20, 60),
    "glute_bridges": ("functional_strength_training", "Functional Strength Training", 30, 90),
    "side_leg_raises": ("functional_strength_training", "Functional Strength Training", 45, 120),
    "dead_bug": ("core_training", "Core Training", 45, 120),
    "bird_dog": ("core_training", "Core Training", 45, 120),
    "calf_raises": ("functional_strength_training", "Functional Strength Training", 20, 75),
    "walk": ("walking", "Walking", 120, 180),
    "wall_angels": ("flexibility", "Flexibility", 30, 90),
}
DEFAULT_HEALTH_PROFILE = ("functional_strength_training", "Functional Strength Training", 30, 90)


def _config_path() -> Path:
    return store.data_dir() / CONFIG_NAME


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    path = _config_path()
    if path.exists():
        try:
            raw = json.loads(path.read_text())
            if isinstance(raw, dict):
                cfg.update(raw)
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


def save_config(cfg: dict) -> None:
    store.data_dir().mkdir(parents=True, exist_ok=True)
    path = _config_path()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{CONFIG_NAME}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def set_enabled(enabled: bool) -> dict:
    cfg = load_config()
    cfg["enabled"] = bool(enabled)
    save_config(cfg)
    return cfg


def outbox_dir() -> Path:
    override = os.environ.get("VIBE_CRUNCH_HEALTH_SYNC_DIR")
    if override:
        return Path(override).expanduser()
    return (
        Path.home()
        / "Library"
        / "Mobile Documents"
        / "com~apple~CloudDocs"
        / "VibeCrunch"
        / "HealthSync"
        / "outbox"
    )


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _duration_seconds(offer: dict, completed_ts: float, min_sec: int, max_sec: int) -> int:
    try:
        elapsed = completed_ts - float(offer.get("created_ts", completed_ts))
    except (TypeError, ValueError):
        elapsed = (min_sec + max_sec) / 2
    if elapsed <= 0:
        elapsed = min_sec
    return int(round(max(min_sec, min(max_sec, elapsed))))


def build_completion_event(offer: dict, completed_ts: float | None = None) -> dict:
    completed_ts = time.time() if completed_ts is None else float(completed_ts)
    exercise = str(offer.get("exercise") or "unknown")
    workout_key, workout_label, min_sec, max_sec = EXERCISE_HEALTH_PROFILE.get(
        exercise, DEFAULT_HEALTH_PROFILE
    )
    duration_sec = _duration_seconds(offer, completed_ts, min_sec, max_sec)
    start_ts = completed_ts - duration_sec
    return {
        "schema_version": "1.0",
        "source": "vibe-crunch",
        "event_id": str(offer.get("id") or f"manual-{int(completed_ts * 1000)}"),
        "exercise": exercise,
        "exercise_label": str(offer.get("label") or exercise),
        "target": str(offer.get("target") or ""),
        "sets": int(offer.get("sets") or 1),
        "workout_type": workout_key,
        "shortcuts_workout_type": workout_label,
        "start_at": _iso(start_ts),
        "completed_at": _iso(completed_ts),
        "duration_seconds": duration_sec,
    }


def enqueue_completion(offer: dict, completed_ts: float | None = None) -> Path:
    event = build_completion_event(offer, completed_ts)
    directory = outbox_dir()
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / f"{event['event_id']}.json"
    # Resolving an offer is already idempotent, but keep the event writer
    # idempotent too. Replays overwrite the exact same event, never create a
    # second filename that the iPhone could log twice.
    fd, tmp = tempfile.mkstemp(dir=str(directory), prefix=".vibe-crunch-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(event, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, final)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return final


def pending_count() -> int:
    try:
        return sum(1 for p in outbox_dir().glob("*.json") if p.is_file())
    except OSError:
        return 0


def shortcut_available(name: str | None = None) -> bool:
    if sys.platform != "darwin":
        return False
    name = name or str(load_config().get("trigger_shortcut") or DEFAULT_SHORTCUT)
    try:
        proc = subprocess.run(
            ["/usr/bin/shortcuts", "list"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    return name in {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def trigger_async(name: str | None = None) -> bool:
    if sys.platform != "darwin":
        return False
    name = name or str(load_config().get("trigger_shortcut") or DEFAULT_SHORTCUT)
    try:
        subprocess.Popen(
            ["/usr/bin/shortcuts", "run", name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return True
    except OSError:
        return False


def sync_completion(offer: dict, completed_ts: float | None = None) -> bool:
    cfg = load_config()
    if not cfg.get("enabled", False):
        return False
    enqueue_completion(offer, completed_ts)
    # Trigger failure is intentionally non-fatal. The durable outbox is the
    # source of truth; a later trigger can flush all queued events.
    trigger_async(str(cfg.get("trigger_shortcut") or DEFAULT_SHORTCUT))
    return True


def status_text() -> str:
    cfg = load_config()
    name = str(cfg.get("trigger_shortcut") or DEFAULT_SHORTCUT)
    enabled = bool(cfg.get("enabled", False))
    lines = [
        f"Apple 健康同步：{'已开启' if enabled else '未开启'}",
        f"传输：iCloud Drive + Focus + Shortcuts",
        f"Mac 触发快捷指令：{name}",
        f"待同步事件：{pending_count()} 条",
    ]
    if sys.platform == "darwin":
        lines.append(f"快捷指令检测：{'已找到' if shortcut_available(name) else '未找到'}")
    return "\n".join(lines)
