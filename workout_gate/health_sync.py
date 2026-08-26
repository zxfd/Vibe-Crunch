"""Bridge completed Vibe Crunch sessions from macOS to iPhone HealthKit.

macOS exposes the HealthKit framework but cannot access the Health database, so
Vibe Crunch cannot write Apple Health directly from the Mac. The zero-server
bridge keeps the Mac side tiny and fail-open:

    Vibe Crunch done
      -> write one immutable-ish JSON event into iCloud Drive (audit/backfill)
      -> run macOS Shortcut "Vibe Crunch Health Sync" with that JSON as input
      -> the Shortcut turns on one of four shared Focus signals
      -> iPhone personal automation wakes from that Focus and logs the workout

The iPhone does NOT need to read the iCloud JSON to perform the Health write.
That matters because file access while the phone is locked is less reliable than
the Focus trigger itself. The JSON ledger is retained so exact exercise/target/
event IDs are never lost and can support a richer companion app or backfill
later.

The bridge is disabled by default. A broken or missing shortcut must never block
Vibe Crunch's local completion flow.
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
    "transport": "icloud-ledger+focus-category-shortcuts",
    "trigger_shortcut": DEFAULT_SHORTCUT,
}

# Four intentionally coarse signals keep the one-time iPhone setup reasonable.
# The iPhone helper shortcut maps these Focus names to native Apple Health
# workout categories. Exact exercise details remain in the JSON event ledger.
FOCUS_SIGNALS = {
    "functional_strength_training": "Vibe Sync Strength",
    "core_training": "Vibe Sync Core",
    "walking": "Vibe Sync Walk",
    "flexibility": "Vibe Sync Mobility",
}

# Apple Health workout categories. We deliberately do NOT fabricate calories,
# heart rate, or distance. The JSON keeps a conservative elapsed-duration
# estimate for audit/backfill; the no-payload Focus MVP logs a fixed conservative
# duration per category on the iPhone (documented in docs/apple-health-sync.md).
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


def event_dir() -> Path:
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
        / "events"
    )


# Backwards-compatible internal name for the first draft of the bridge.
def outbox_dir() -> Path:
    return event_dir()


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
        "schema_version": "1.1",
        "source": "vibe-crunch",
        "event_id": str(offer.get("id") or f"manual-{int(completed_ts * 1000)}"),
        "exercise": exercise,
        "exercise_label": str(offer.get("label") or exercise),
        "target": str(offer.get("target") or ""),
        "sets": int(offer.get("sets") or 1),
        "workout_type": workout_key,
        "shortcuts_workout_type": workout_label,
        "signal_focus": FOCUS_SIGNALS.get(workout_key, FOCUS_SIGNALS["functional_strength_training"]),
        "start_at": _iso(start_ts),
        "completed_at": _iso(completed_ts),
        "duration_seconds": duration_sec,
    }


def enqueue_completion(offer: dict, completed_ts: float | None = None) -> Path:
    event = build_completion_event(offer, completed_ts)
    directory = event_dir()
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / f"{event['event_id']}.json"
    # Resolving an offer is already idempotent, but keep the event writer
    # idempotent too. A replay overwrites the exact same event file rather than
    # creating a second ledger entry.
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


def event_count() -> int:
    try:
        return sum(1 for p in event_dir().glob("*.json") if p.is_file())
    except OSError:
        return 0


# Compatibility alias used by micro.py from the first implementation pass.
def pending_count() -> int:
    return event_count()


def latest_event_path() -> Path | None:
    try:
        files = [p for p in event_dir().glob("*.json") if p.is_file()]
    except OSError:
        return None
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


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


def trigger_async(event_path: Path | str | None = None, name: str | None = None) -> bool:
    """Run the Mac bridge shortcut, passing the exact event JSON as File input."""
    if sys.platform != "darwin":
        return False
    name = name or str(load_config().get("trigger_shortcut") or DEFAULT_SHORTCUT)
    path = Path(event_path) if event_path is not None else latest_event_path()
    if path is None or not path.exists():
        return False
    try:
        subprocess.Popen(
            ["/usr/bin/shortcuts", "run", name, "-i", str(path)],
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
    event_path = enqueue_completion(offer, completed_ts)
    # The ledger write happens first. If the Shortcut/Focus path is temporarily
    # broken, the exact event is still available for diagnosis/backfill.
    trigger_async(event_path, str(cfg.get("trigger_shortcut") or DEFAULT_SHORTCUT))
    return True


def status_text() -> str:
    cfg = load_config()
    name = str(cfg.get("trigger_shortcut") or DEFAULT_SHORTCUT)
    enabled = bool(cfg.get("enabled", False))
    lines = [
        f"Apple 健康同步：{'已开启' if enabled else '未开启'}",
        "传输：Mac Shortcut → 共享 Focus → iPhone Shortcut → HealthKit",
        f"Mac 触发快捷指令：{name}",
        f"iCloud 事件账本：{event_count()} 条",
    ]
    if sys.platform == "darwin":
        lines.append(f"快捷指令检测：{'已找到' if shortcut_available(name) else '未找到'}")
    return "\n".join(lines)
