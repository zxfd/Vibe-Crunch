"""Opt-in, local-only resistance-training plan. No personal health data or UI.

The prescription is a conservative starting template, not medical clearance.
Completed cards are self-reported prescribed sets, not sensor-measured volume.
"""
from __future__ import annotations

import datetime as dt
import random
import time
import uuid

EXERCISES = {
    "pushups": ("上斜俯卧撑", 6, 12, False,
        "双手撑牢固、不滑动的高台或墙；身体成直线。太难就提高支撑面，不硬凑次数。"),
    "band_rows": ("支撑式背包 / 弹力带划船", 8, 15, True,
        "用轻且封好的背包，另一手支撑牢固台面；肘向后拉、不耸肩。弹力带需确认完好且固定可靠。"),
    "chair_squats": ("扶稳高椅坐站", 6, 12, False,
        "椅子靠墙防滑，可扶牢固台面；只在无痛范围慢坐慢起。膝痛、肿胀或卡住就停止，不做深蹲替代。"),
    "glute_bridges": ("臀桥", 10, 20, False,
        "仰卧屈膝、脚踩稳；臀部发力抬起，不过度挺腰，顶端停一秒。腰或膝不适就停止。"),
    "lateral_raises": ("轻水瓶侧平举", 10, 20, False,
        "用轻水瓶或徒手，肘微屈；不耸肩、不甩动，抬到舒适高度即可，肩痛就停止。"),
    "dead_bug": ("死虫式", 6, 10, True,
        "仰卧，下背保持稳定；缓慢伸出对侧手脚。腰拱起就缩小幅度，不憋气。"),
}
ORDER = tuple(EXERCISES)  # stable reporting order only; scheduling is random
FEEDBACK = ("easy", "good", "hard", "pain")
REST_HOURS = 48


def day_key(now: float) -> str:
    return dt.datetime.fromtimestamp(now).date().isoformat()


def _data(state: dict) -> dict:
    data = state.setdefault("lean", {})
    for key in ("history", "blocked"):
        data.setdefault(key, [])
    for key in ("reps", "easy_streak"):
        data.setdefault(key, {})
    return data


def day_index(state: dict, now: float) -> int:
    data = _data(state)
    data.setdefault("start_date", day_key(now))
    return (dt.date.fromisoformat(day_key(now)) - dt.date.fromisoformat(data["start_date"])).days


def is_strength_day(state: dict, now: float) -> bool:
    index = day_index(state, now)
    return index >= 0 and index % 7 in (0, 2, 4)


def _reset_day(state: dict, now: float) -> None:
    today = day_key(now)
    if state.get("micro_day") != today:
        state.update(micro_day=today, micro_auto_offers_today=0,
                     micro_completed_today=0, micro_rest_day=None)
    state.setdefault("micro_auto_offers_today", 0)
    state.setdefault("micro_completed_today", 0)
    # This used to drive deterministic lean rotation. Keep old state harmless
    # after upgrading from earlier builds instead of letting it influence picks.
    state.pop("lean_rotation", None)


def eligible_exercises(state: dict, now: float) -> list[str]:
    data = _data(state)
    today = day_key(now)
    completed = [r for r in data["history"] if r.get("completed") or r.get("feedback") == "hard"]
    if not is_strength_day(state, now):
        if "recovery_walk" in data["blocked"]:
            return []
        if any(r["day"] == today and r["exercise"] == "recovery_walk" for r in completed):
            return []
        return ["recovery_walk"]
    result = []
    for name in ORDER:
        if name in data["blocked"]:
            continue
        records = [r for r in completed if r["exercise"] == name]
        if any(r["day"] == today or now - r["ts"] < REST_HOURS * 3600 for r in records):
            continue
        result.append(name)
    return result


def _pick_random(candidates: list[str], exclude: str | None = None) -> str | None:
    pool = [name for name in candidates if name != exclude]
    if not pool:
        pool = list(candidates)
    return random.choice(pool) if pool else None


def _prescription(state: dict, name: str, now: float) -> dict:
    if name == "recovery_walk":
        return dict(exercise=name, label="恢复日：轻松平地走动", sets=1,
                    target="2–5 分钟，舒服即可", reps=0, kind="recovery",
                    cue="不是增肌训练，不计力量组数。可以与出门办事结合；疼痛、肿胀或明显疲劳时直接休息。")
    label, low, high, per_side, cue = EXERCISES[name]
    data = _data(state)
    records = [r for r in data["history"] if r["exercise"] == name]
    records = records[int(data.get("resume_after", {}).get(name, 0)): ]
    # One set for the first week. Later, require two positive reports and no
    # intervening hard report before doubling sets. Missing feedback never advances.
    positive_run = 0
    for record in reversed(records):
        if record.get("feedback") not in ("easy", "good"):
            break
        positive_run += 1
    sets = 2 if day_index(state, now) >= 7 and positive_run >= 2 else 1
    reps = max(low, min(high, int(data["reps"].get(name, low))))
    if reps == high:
        cue += " 已到次数上限：先保持，结合周报评估是否调阻力；程序不自动加重量。"
    target = f"{'每侧 ' if per_side else ''}{reps} 次/组"
    return dict(exercise=name, label=label, sets=sets, target=target,
                reps=reps, kind="strength", cue=cue)


def plan_offer(config: dict, state: dict, source: str, now: float, force: bool = False):
    _reset_day(state, now)
    _data(state)
    if not config.get("enabled", False) or state.get("micro_rest_day") == day_key(now):
        return None
    if state.pop("micro_return_pending", False):
        state["micro_last_return_ts"] = now
        if not force:
            state["micro_last_offer_ts"] = now
            return None
    if not force and not 14 <= dt.datetime.fromtimestamp(now).hour < 23:
        return None
    pending = state.get("micro_pending")
    if pending:
        age = now - float(pending.get("created_ts", now))
        if pending.get("day") == day_key(now) and age < max(1, int(config.get("stale_after_min", 90))) * 60:
            return None
        state["micro_pending"] = None
    if not force:
        last = float(state.get("micro_last_offer_ts", 0) or 0)
        if last and now - last < max(0, int(config.get("cooldown_min", 30))) * 60:
            return None
    candidates = eligible_exercises(state, now)
    if not candidates:
        return None
    name = _pick_random(candidates)
    offer = dict(id=uuid.uuid4().hex, program="lean", source=source,
                 created_ts=now, day=day_key(now), **_prescription(state, name, now))
    state.update(micro_pending=offer, micro_last_offer_ts=now)
    if not force:
        state["micro_auto_offers_today"] += 1
    return offer


def swap_offer(state: dict, offer_id: str, now: float):
    pending = state.get("micro_pending")
    if not pending or pending["id"] != offer_id or pending.get("day") != day_key(now):
        return None
    candidates = eligible_exercises(state, now)
    name = _pick_random(candidates, exclude=pending["exercise"])
    if not name or name == pending["exercise"]:
        return pending
    pending.update(_prescription(state, name, now))
    return pending


def apply_action(state: dict, offer_id: str, action: str, now: float, feedback=None):
    if action not in ("done", "skip", "rest", "timeout"):
        raise ValueError("invalid action")
    if feedback is not None and feedback not in FEEDBACK:
        raise ValueError("invalid training feedback")
    pending = state.get("micro_pending")
    if not pending or pending["id"] != offer_id:
        return None
    if pending["day"] != day_key(now):
        state["micro_pending"] = None
        return None
    _reset_day(state, now)
    data = _data(state)
    if feedback == "pain":
        action = "skip"
        name = pending["exercise"]
        if name not in data["blocked"]:
            data["blocked"].append(name)
        state["micro_rest_day"] = day_key(now)
    if feedback == "hard":
        action = "skip"  # Partial/too-hard attempts must not inflate completed sets.
    completed = action == "done"
    record = dict(id=offer_id, exercise=pending["exercise"], day=day_key(now), ts=now,
                  sets=pending["sets"] if completed and pending["kind"] == "strength" else 0,
                  reps=pending["reps"], kind=pending["kind"], completed=completed,
                  feedback=feedback, action=action)
    data["history"].append(record)
    name = record["exercise"]
    if (completed or feedback == "hard") and record["kind"] == "strength":
        low, high = EXERCISES[name][1:3]
        current = max(low, min(high, int(data["reps"].get(name, low))))
        if feedback == "easy":
            streak = int(data["easy_streak"].get(name, 0)) + 1
            if streak >= 2:
                data["reps"][name] = min(high, current + 1)
                streak = 0
            data["easy_streak"][name] = streak
        else:
            data["easy_streak"][name] = 0
            if feedback == "hard":
                data["reps"][name] = max(low, current - 2)
    elif feedback == "pain":
        data["easy_streak"][name] = 0
    state.update(micro_pending=None, micro_last_action=action, micro_last_action_ts=now)
    if completed:
        state["micro_completed_today"] += 1
    if action == "timeout":
        state["micro_return_pending"] = True
    if action == "rest":
        state["micro_rest_day"] = day_key(now)
    return pending


def resume_exercise(state: dict, name: str) -> None:
    if name not in EXERCISES and name != "recovery_walk":
        raise ValueError("unknown exercise")
    data = _data(state)
    data["blocked"] = [n for n in data["blocked"] if n != name]
    data.setdefault("resume_after", {})[name] = sum(r["exercise"] == name for r in data["history"])
    if name in EXERCISES:
        data["reps"][name] = EXERCISES[name][1]
        data["easy_streak"][name] = 0
    # Never override today's rest or the 48-hour recovery guard.


def report_text(state: dict, now=None) -> str:
    now = time.time() if now is None else now
    # Reporting is read-only, including before the first program activation.
    import copy
    state = copy.deepcopy(state)
    data = _data(state)
    today = day_key(now)
    start = (dt.date.fromisoformat(today) - dt.timedelta(days=6)).isoformat()
    records = [r for r in data["history"] if start <= r["day"] <= today]
    done = [r for r in records if r.get("completed")]
    strength = [r for r in done if r["kind"] == "strength"]
    today_done = sum(r["day"] == today for r in done)
    kind = "力量日" if is_strength_day(state, now) else "恢复日"
    lines = [f"薄肌入门计划｜第 {max(0, day_index(state, now)) + 1} 天｜{kind}",
             f"今日完成卡片：{today_done}；当前可做：{len(eligible_exercises(state, now))}",
             "自动提醒：本机时间 14:00–23:00，仅在提交 AI 任务时检查；不是定时闹钟。",
             "力量日动作从当前安全且已恢复的候选中随机抽取；同动作完成/过难后当天不重复，且保留 48 小时恢复间隔。",
             "前 7 天每动作 1 组；之后按反馈决定是否到 2 组。漏练不补债。",
             f"近 7 天：力量卡片 {len(strength)}，力量组数 {sum(r['sets'] for r in strength)}，"
             f"恢复卡片 {len(done) - len(strength)}。",
             "以上为按完成按钮记录的处方组数，不是传感器测量。"]
    for name, spec in EXERCISES.items():
        sets = sum(r["sets"] for r in strength if r["exercise"] == name)
        lines.append(f"  {spec[0]}：{sets} 组；下次目标 {data['reps'].get(name, spec[1])} 次/组")
    hard = sum(r.get("feedback") == "hard" for r in records)
    lines.append(f"太难 / 未完成：{hard} 次（不计满组，但保留恢复间隔）。")
    pains = sum(r.get("feedback") == "pain" for r in records)
    lines.append(f"疼痛反馈：{pains} 次；已暂停动作：{', '.join(data['blocked']) or '无'}")
    lines.append("疼痛暂停不等于诊断；恢复前确认症状已解决或取得专业指导。")
    return "\n".join(lines)
