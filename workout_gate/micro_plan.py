"""Keep scheduling pure so hook policy can be tested without UI or persistence dependencies."""
from __future__ import annotations

import datetime
import random
import time
import uuid

MICRO_EXERCISES = {
    "pushups": {
        "label": "俯卧撑",
        "sets": 1,
        "target": "4–6 次",
        "cue": "身体保持一条直线，下降到舒适深度；不要做到力竭，至少留 2 次余力。",
    },
    "wall_sit": {
        "label": "靠墙静蹲",
        "sets": 1,
        "target": "20–30 秒",
        "cue": "背靠墙，膝屈曲保持舒适的浅到中等角度，不追求蹲到 90°；膝部出现疼痛、卡住或明显不适就停止。",
    },
    "plank": {
        "label": "平板支撑",
        "sets": 1,
        "target": "30–40 秒",
        "cue": "收紧腹部和臀部，保持自然呼吸；腰开始塌或明显代偿就提前结束。",
    },
    "glute_bridges": {
        "label": "臀桥",
        "sets": 1,
        "target": "12–15 次",
        "cue": "顶端夹紧臀部停约 1 秒；动作来自髋部，不要为了抬得更高而过度挺腰。",
    },
    "dead_bug": {
        "label": "死虫式",
        "sets": 1,
        "target": "每侧 6–8 次",
        "cue": "下背轻贴地，收紧核心；手脚慢慢伸远，腰一旦离地就缩小动作幅度。",
    },
    "bird_dog": {
        "label": "鸟狗式",
        "sets": 1,
        "target": "每侧 6–8 次",
        "cue": "四点支撑，缓慢伸直对侧手脚；骨盆尽量稳定，不要为了抬高而扭腰。",
    },
    "calf_raises": {
        "label": "站姿提踵",
        "sets": 1,
        "target": "15–20 次",
        "cue": "扶墙保持平衡，脚跟缓慢抬起再落下；不要弹震，顶端短暂停顿。",
    },
    "walk": {
        "label": "离座走动",
        "sets": 1,
        "target": "2–3 分钟",
        "cue": "离开座位，在家里正常走动；重点是打断久坐，不要求快走或追求心率。",
    },
    "wall_angels": {
        "label": "墙天使",
        "sets": 1,
        "target": "8–12 次",
        "cue": "背靠墙，手臂在舒适范围内缓慢上下滑动；不要耸肩，也不强求手背始终贴墙。",
    },
}


def default_micro_config() -> dict:
    return {
        "enabled": True,
        "cooldown_min": 30,
        "daily_goal": 5,
        "stale_after_min": 90,
        "exercise_pool": list(MICRO_EXERCISES),
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
    state.pop("micro_rotation_index", None)


def _exercise_pool(micro: dict) -> list[str]:
    pool = [name for name in micro.get("exercise_pool", []) if name in MICRO_EXERCISES]
    return pool or list(MICRO_EXERCISES)


def _random_exercise(pool: list[str], exclude: str | None = None) -> str:
    candidates = [name for name in pool if name != exclude]
    return random.choice(candidates or pool)


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

    pool = _exercise_pool(micro)
    name = _random_exercise(pool)
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
    state["micro_last_offer_ts"] = now
    if not force:
        state["micro_auto_offers_today"] = int(state.get("micro_auto_offers_today", 0)) + 1
    return offer


def swap_pending_offer(config: dict, state: dict, offer_id: str):
    """Randomly replace the pending exercise without creating a new cooldown or reminder event."""
    pending = state.get("micro_pending")
    if not pending or pending.get("id") != offer_id:
        return None

    micro = config.get("micro") or {}
    pool = _exercise_pool(micro)
    name = _random_exercise(pool, exclude=pending.get("exercise"))
    spec = MICRO_EXERCISES[name]
    pending.update(
        exercise=name,
        label=spec["label"],
        sets=spec["sets"],
        target=spec["target"],
        cue=spec["cue"],
    )
    return pending


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
