"""Keep scheduling pure so hook policy can be tested without UI or persistence dependencies."""
from __future__ import annotations

import datetime
import time
import uuid

MICRO_EXERCISES = {
    "pushups": {
        "label": "俯卧撑",
        "sets": 2,
        "target": "8–12 次/组",
        "cue": "身体保持一条直线，下降到舒适深度；动作稳定，每组留 2–4 次余力。",
    },
    "band_rows": {
        "label": "弹力带 / 背包划船",
        "sets": 2,
        "target": "12–15 次/组",
        "cue": "肩胛向后收，肘部向后拉；不要耸肩，动作慢一点。",
    },
    "chair_squats": {
        "label": "椅子深蹲",
        "sets": 2,
        "target": "10–15 次/组",
        "cue": "缓慢下坐轻触椅面，再站起；保持动作稳定，不要追求速度。",
    },
    "glute_bridges": {
        "label": "臀桥",
        "sets": 2,
        "target": "12–20 次/组",
        "cue": "顶端夹紧臀部停约 1 秒；不要为了抬得更高而过度挺腰。",
    },
    "dead_bug": {
        "label": "死虫式",
        "sets": 2,
        "target": "每侧 8–10 次/组",
        "cue": "下背轻贴地，收紧核心；动作放慢，左右交替。",
    },
}


def default_micro_config() -> dict:
    return {
        "enabled": True,
        "cooldown_min": 30,
        "daily_goal": 5,
        "stale_after_min": 90,
        "exercise_order": list(MICRO_EXERCISES),
    }


def _day_key(now: float) -> str:
    return datetime.datetime.fromtimestamp(now).date().isoformat()


def _reset_daily_state(state: dict, day: str) -> None:
    if state.get("micro_day") != day:
        state["micro_day"] = day
        state["micro_auto_offers_today"] = 0
        state["micro_completed_today"] = 0
        state["micro_rest_day"] = None
    else:
        state.setdefault("micro_auto_offers_today", 0)
        state.setdefault("micro_completed_today", 0)
    state.pop("micro_offers_today", None)


def plan_offer(
    config: dict,
    state: dict,
    source: str = "codex",
    now: float | None = None,
    force: bool = False,
):
    """Manual runs bypass scheduling guards but still count when completed."""
    micro = config.get("micro") or {}
    if not micro.get("enabled", False):
        return None

    now = time.time() if now is None else now
    day = _day_key(now)
    _reset_daily_state(state, day)

    if state.get("micro_rest_day") == day and not force:
        return None

    pending = state.get("micro_pending")
    if pending:
        if force:
            state["micro_pending"] = None
        else:
            age = now - float(pending.get("created_ts", now))
            stale_after = max(1, int(micro.get("stale_after_min", 90))) * 60
            if age < stale_after:
                return None
            state["micro_pending"] = None

    if not force:
        daily_goal = max(1, int(micro.get("daily_goal", 5)))
        if int(state.get("micro_completed_today", 0)) >= daily_goal:
            return None

        cooldown = max(0, int(micro.get("cooldown_min", 30))) * 60
        last = float(state.get("micro_last_offer_ts", 0) or 0)
        if last > 0 and now - last < cooldown:
            return None

    order = [name for name in micro.get("exercise_order", []) if name in MICRO_EXERCISES]
    if not order:
        order = list(MICRO_EXERCISES)
    idx = int(state.get("micro_rotation_index", 0)) % len(order)
    name = order[idx]
    spec = MICRO_EXERCISES[name]
    offer = {
        "id": uuid.uuid4().hex,
        "exercise": name,
        "label": spec["label"],
        "sets": spec["sets"],
        "target": spec["target"],
        "cue": spec["cue"],
        "source": source,
        "created_ts": now,
        "day": day,
    }

    state["micro_pending"] = offer
    state["micro_rotation_index"] = (idx + 1) % len(order)
    state["micro_last_offer_ts"] = now
    if not force:
        state["micro_auto_offers_today"] = int(state.get("micro_auto_offers_today", 0)) + 1
    return offer


def apply_action(state: dict, offer_id: str, action: str, now: float | None = None):
    if action not in ("done", "skip", "rest"):
        raise ValueError(f"unsupported micro action: {action}")
    pending = state.get("micro_pending")
    if not pending or pending.get("id") != offer_id:
        return None
    now = time.time() if now is None else now
    _reset_daily_state(state, _day_key(now))
    state["micro_pending"] = None
    state["micro_last_action"] = action
    state["micro_last_action_ts"] = now
    if action == "done":
        state["micro_completed_today"] = int(state.get("micro_completed_today", 0)) + 1
    elif action == "rest":
        state["micro_rest_day"] = _day_key(now)
    return pending


def describe_offer(offer: dict) -> str:
    return f"{offer['label']} — {offer['sets']} 组，{offer['target']}"
