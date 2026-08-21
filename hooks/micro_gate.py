#!/usr/bin/env python3
"""Detach reminder UI so UserPromptSubmit can return without gating the AI task."""
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from workout_gate import micro, store  # noqa: E402


def log(msg: str) -> None:
    try:
        with (store.data_dir() / "gate.log").open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [vibe-crunch] {msg}\n")
    except OSError:
        pass


def _is_escape(prompt: str) -> bool:
    p = prompt.strip().lower()
    return (
        p.startswith("/workout")
        or p in ("workout", "wg", "vibe-crunch", "vibe crunch")
        or p.startswith("workout ")
        or p.startswith("wg ")
        or p.startswith("vibe-crunch ")
        or p.startswith("vibe crunch ")
    )


def _source(payload: dict) -> str:
    env = os.environ.get("WORKOUT_GATE_SOURCE")
    if env:
        return env.lower()
    if os.environ.get("PLUGIN_ROOT"):
        return "codex"
    model = (payload.get("model") or "").lower()
    if model and not model.startswith("claude"):
        return "codex"
    return "claude"


def duplicate_invocation(payload: dict, window_s: float = 5.0) -> bool:
    raw = (
        f"{payload.get('session_id', '')}:{payload.get('turn_id', '')}:"
        f"{payload.get('prompt', '')}"
    )
    key = hashlib.md5(raw.encode()).hexdigest()
    path = store.data_dir() / "last-vibe-crunch"
    now = time.time()
    with store.locked("vibe-crunch-hook.lock"):
        try:
            prev_key, prev_ts = path.read_text().split(" ")
            if prev_key == key and now - float(prev_ts) < window_s:
                return True
        except (OSError, ValueError):
            pass
        path.write_text(f"{key} {now}")
    return False


def main() -> int:
    if os.environ.get("VIBE_CRUNCH_OFF") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}
    if _is_escape(payload.get("prompt") or ""):
        return 0
    if duplicate_invocation(payload):
        return 0
    if not micro.enabled():
        return 0

    offer = micro.prepare_offer(_source(payload))
    if not offer:
        return 0
    try:
        micro.spawn_prompt(offer)
    except Exception:
        # Clear pending state immediately so a failed UI launch cannot suppress reminders for 90 minutes.
        micro.resolve_offer(offer["id"], "skip")
        raise
    # UserPromptSubmit stdout becomes model-visible developer context in Codex, so successful hooks stay silent.
    log(f"offered {offer['exercise']} id={offer['id']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log("FAIL-OPEN:\n" + traceback.format_exc())
        raise SystemExit(0)
