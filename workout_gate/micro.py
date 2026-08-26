"""Keep Vibe Crunch micro-workout state isolated from retained upstream compatibility code."""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import subprocess
import sys
import tempfile
import time
from typing import Optional

from . import health_sync, store
from .micro_plan import (
    MICRO_EXERCISES,
    apply_action,
    default_micro_config,
    describe_offer,
    plan_offer,
    swap_pending_offer,
)

CONFIG_NAME = "vibe-crunch.json"
STATE_NAME = "vibe-crunch-state.json"
STATS_NAME = "vibe-crunch-stats.json"

DEFAULT_STATS = {
    "offered": 0,
    "completed": 0,
    "skipped": 0,
    "rested": 0,
    "by_day": {},
    "by_exercise": {},
}


def _path(name: str):
    return store.data_dir() / name


def _load(name: str, defaults: dict) -> dict:
    path = _path(name)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    out = copy.deepcopy(defaults)
    out.update(data)
    return out


def _save(name: str, data: dict) -> None:
    path = _path(name)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def load_config() -> dict:
    cfg = _load(CONFIG_NAME, default_micro_config())
    defaults = default_micro_config()
    for key, value in defaults.items():
        cfg.setdefault(key, copy.deepcopy(value))
    cfg.pop("daily_max", None)
    cfg.pop("exercise_order", None)  # legacy deterministic-rotation setting
    return cfg


def save_config(cfg: dict) -> None:
    cfg.pop("daily_max", None)
    cfg.pop("exercise_order", None)
    _save(CONFIG_NAME, cfg)


def load_state() -> dict:
    state = _load(STATE_NAME, {})
    today = store.today()
    if state.get("micro_day") == today:
        if "micro_completed_today" not in state:
            stats = load_stats()
            state["micro_completed_today"] = int(
                stats.get("by_day", {}).get(today, {}).get("completed", 0)
            )
        state.setdefault("micro_auto_offers_today", 0)
    state.pop("micro_offers_today", None)
    state.pop("micro_rotation_index", None)
    return state


def save_state(state: dict) -> None:
    state.pop("micro_offers_today", None)
    state.pop("micro_rotation_index", None)
    _save(STATE_NAME, state)


def load_stats() -> dict:
    stats = _load(STATS_NAME, DEFAULT_STATS)
    stats.setdefault("by_day", {})
    stats.setdefault("by_exercise", {})
    return stats


def _mutate_state(mutator):
    with store.locked("vibe-crunch.lock"):
        state = load_state()
        result = mutator(state)
        save_state(state)
    return result


def _mutate_stats(mutator):
    with store.locked("vibe-crunch-stats.lock"):
        stats = load_stats()
        result = mutator(stats)
        _save(STATS_NAME, stats)
    return result


def enabled() -> bool:
    if os.environ.get("VIBE_CRUNCH_OFF") == "1":
        return False
    return bool(load_config().get("enabled", True))


def _record_offer(offer: dict) -> None:
    def _record(stats):
        stats["offered"] = int(stats.get("offered", 0)) + 1
        day = stats.setdefault("by_day", {}).setdefault(offer["day"], {})
        day["offered"] = int(day.get("offered", 0)) + 1
        ex = stats.setdefault("by_exercise", {}).setdefault(
            offer["exercise"], {"offered": 0, "completed": 0, "skipped": 0, "rested": 0}
        )
        ex["offered"] = int(ex.get("offered", 0)) + 1
    _mutate_stats(_record)


def prepare_offer(
    source: str = "codex",
    now: float | None = None,
    force: bool = False,
):
    cfg = load_config()
    if os.environ.get("VIBE_CRUNCH_OFF") == "1":
        return None

    def _plan(state):
        return plan_offer({"micro": cfg}, state, source=source, now=now, force=force)

    offer = _mutate_state(_plan)
    if offer:
        _record_offer(offer)
    return offer


def _record_action(offer: dict, action: str) -> None:
    field = {"done": "completed", "skip": "skipped", "rest": "rested"}[action]

    def _record(stats):
        stats[field] = int(stats.get(field, 0)) + 1
        day = stats.setdefault("by_day", {}).setdefault(offer["day"], {})
        day[field] = int(day.get(field, 0)) + 1
        ex = stats.setdefault("by_exercise", {}).setdefault(
            offer["exercise"], {"offered": 0, "completed": 0, "skipped": 0, "rested": 0}
        )
        ex[field] = int(ex.get(field, 0)) + 1
    _mutate_stats(_record)


def resolve_offer(offer_id: str, action: str):
    # Use one timestamp for both the local completion record and the HealthKit
    # bridge so the two stores describe the same event.
    completed_ts = time.time()

    def _apply(state):
        return apply_action(state, offer_id, action, now=completed_ts)

    offer = _mutate_state(_apply)
    if offer:
        _record_action(offer, action)
        if action == "done":
            # Health sync is fail-open by design. A disabled bridge is a no-op;
            # once enabled it first writes a durable iCloud outbox event, then
            # best-effort triggers the iPhone automation.
            try:
                health_sync.sync_completion(offer, completed_ts)
            except Exception:
                pass
    return offer


def swap_offer(offer_id: str):
    cfg = load_config()

    def _swap(state):
        return swap_pending_offer({"micro": cfg}, state, offer_id)

    return _mutate_state(_swap)


def _pending(offer_id: str):
    state = load_state()
    offer = state.get("micro_pending")
    return offer if offer and offer.get("id") == offer_id else None


def _display_offer(offer: dict) -> dict:
    """Resolve UI copy from current specs so persisted offers do not freeze presentation strings."""
    spec = MICRO_EXERCISES.get(offer.get("exercise"), {})
    shown = dict(offer)
    for key in ("label", "sets", "target", "cue"):
        if key in spec:
            shown[key] = spec[key]
    return shown


def _describe_display_offer(offer: dict) -> str:
    return describe_offer(_display_offer(offer))


def _dialog_message(offer: dict) -> str:
    offer = _display_offer(offer)
    actor = (offer.get("source") or "AI").upper()
    return (
        f"{actor} 正在卷代码，你也卷一下腹吧。\n\n"
        f"本轮：{offer['label']}\n"
        f"做 {offer['sets']} 组，{offer['target']}\n\n"
        f"动作要点：{offer['cue']}\n\n"
        "预计约 30 秒–3 分钟，不做到力竭。\n\n"
        "按钮说明：\n"
        "• 完成了：记录本次训练完成\n"
        "• 换一个：随机换成另一个训练动作，不算跳过\n"
        "• 跳过这次：只跳过当前这一轮，冷却后仍可能继续提醒\n"
        "• 今天休息：今天剩余时间不再提醒"
    )


def _mac_dialog(offer: dict) -> str:
    # NSAlert supports four response buttons; AppleScript display dialog only supports three.
    script = r'''
ObjC.import("AppKit");
function run(argv) {
    const alert = $.NSAlert.new;
    alert.messageText = "Vibe Crunch｜微训练";
    alert.informativeText = argv[0];
    alert.addButtonWithTitle("完成了");
    alert.addButtonWithTitle("跳过这次");
    alert.addButtonWithTitle("换一个");
    alert.addButtonWithTitle("今天休息");
    $.NSApplication.sharedApplication.activateIgnoringOtherApps(true);
    return alert.runModal;
}
'''
    proc = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script, _dialog_message(offer)],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return "skip"
    try:
        response = int(proc.stdout.strip())
    except ValueError:
        return "skip"
    return {
        1000: "done",
        1001: "skip",
        1002: "swap",
        1003: "rest",
    }.get(response, "skip")


def _tk_dialog(offer: dict) -> Optional[str]:
    try:
        os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")
        import tkinter as tk
    except Exception:
        return None

    result = {"action": "skip"}
    try:
        root = tk.Tk()
        root.title("Vibe Crunch｜微训练")
        root.attributes("-topmost", True)
        root.resizable(False, False)
        background = "#1C1C1E"
        root.configure(background=background)
        message = _dialog_message(offer)
        # macOS Tk 8.5 can hide Label/Canvas text in dark mode; native button text stays readable.
        body = tk.Frame(root, padx=12, pady=12, background=background)
        body.pack()
        for line in message.splitlines():
            if line == "按钮说明：":
                break
            if not line:
                tk.Frame(body, height=6, background=background).pack(fill="x")
                continue
            tk.Button(
                body,
                text=line,
                command=lambda: None,
                width=78,
                anchor="w",
                foreground="white",
                activeforeground="white",
                background=background,
                activebackground=background,
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
            ).pack(fill="x")
        row = tk.Frame(root, padx=16, pady=12, background=background)
        row.pack()

        def choose(action):
            result["action"] = action
            root.destroy()

        tk.Button(row, text="今天休息", command=lambda: choose("rest"), width=12).pack(side="left", padx=4)
        tk.Button(row, text="换一个", command=lambda: choose("swap"), width=10).pack(side="left", padx=4)
        tk.Button(row, text="跳过这次", command=lambda: choose("skip"), width=12).pack(side="left", padx=4)
        tk.Button(row, text="完成了", command=lambda: choose("done"), width=10).pack(side="left", padx=4)
        root.protocol("WM_DELETE_WINDOW", lambda: choose("skip"))
        root.update_idletasks()
        width = root.winfo_reqwidth()
        height = root.winfo_reqheight()
        x = max(0, (root.winfo_screenwidth() - width) // 2)
        y = max(0, (root.winfo_screenheight() - height) // 3)
        root.geometry(f"{width}x{height}+{x}+{y}")
        root.lift()
        root.focus_force()
        root.mainloop()
    except Exception:
        return None
    return result["action"]


def prompt_offer(offer_id: str) -> int:
    while True:
        offer = _pending(offer_id)
        if not offer:
            return 0
        action = _tk_dialog(offer)
        if action is None:
            action = _mac_dialog(offer) if sys.platform == "darwin" else "skip"
        if action == "swap":
            if not swap_offer(offer_id):
                return 0
            continue
        resolve_offer(offer_id, action)
        return 0


def _prompt_python() -> str:
    # Homebrew Python may omit Tk; Apple's system Python includes the UI runtime on supported Macs.
    system_python = "/usr/bin/python3"
    if sys.platform == "darwin" and os.access(system_python, os.X_OK):
        return system_python
    return sys.executable


def spawn_prompt(offer: dict) -> None:
    """Detach the UI so UserPromptSubmit can return immediately."""
    from .paths import PROJECT_DIR

    kwargs = {
        "cwd": str(PROJECT_DIR),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "start_new_session": True,
        "close_fds": True,
    }
    subprocess.Popen(
        [_prompt_python(), "-m", "workout_gate.micro", "prompt", offer["id"]],
        **kwargs,
    )


def status_text() -> str:
    cfg, state, stats = load_config(), load_state(), load_stats()
    pending = state.get("micro_pending")
    daily_goal = int(cfg.get("daily_goal", 5))
    pool = [name for name in cfg.get("exercise_pool", []) if name in MICRO_EXERCISES]
    health_cfg = health_sync.load_config()
    lines = [
        f"Vibe Crunch：{'已开启' if cfg.get('enabled', True) else '已关闭'}",
        f"冷却时间：{cfg.get('cooldown_min', 30)} 分钟",
        f"每日完成目标：{daily_goal} 次",
        f"动作选择：完全随机（{len(pool) or len(MICRO_EXERCISES)} 个动作）",
        f"Apple 健康同步：{'已开启' if health_cfg.get('enabled', False) else '未开启'}"
        f"（待同步 {health_sync.pending_count()} 条）",
        f"今日完成：{state.get('micro_completed_today', 0)}/{daily_goal} 次",
        f"今日自动提醒：{state.get('micro_auto_offers_today', 0)} 次",
        f"累计已完成：{stats.get('completed', 0)} 次    累计已跳过：{stats.get('skipped', 0)} 次",
    ]
    if pending:
        lines.append("待处理：" + _describe_display_offer(pending))
    if state.get("micro_rest_day") == state.get("micro_day"):
        lines.append("今天剩余时间：不再提醒")
    return "\n".join(lines)


def _resolve_current(action: str) -> int:
    pending = load_state().get("micro_pending")
    if not pending:
        print("当前没有待处理的微训练。")
        return 0
    offer = resolve_offer(pending["id"], action)
    action_label = {"done": "已完成", "skip": "已跳过", "rest": "今天休息"}[action]
    print(f"{action_label}：{_describe_display_offer(offer)}" if offer else "这条训练提醒已经处理过了。")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="vibe-crunch", description="Vibe Crunch 微训练控制")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status")
    sub.add_parser("on")
    sub.add_parser("off")
    sub.add_parser("now")
    sub.add_parser("done")
    sub.add_parser("skip")
    sub.add_parser("rest")
    p_health = sub.add_parser("health-sync")
    p_health.add_argument("action", choices=["status", "on", "off", "trigger"], nargs="?", default="status")
    p_prompt = sub.add_parser("prompt")
    p_prompt.add_argument("offer_id")
    p_set = sub.add_parser("set")
    p_set.add_argument("key", choices=["cooldown", "daily-goal", "daily-max"])
    p_set.add_argument("value", type=int)
    args = parser.parse_args(argv)

    if args.cmd in (None, "status"):
        print(status_text())
        return 0
    if args.cmd == "health-sync":
        if args.action in ("on", "off"):
            health_sync.set_enabled(args.action == "on")
        elif args.action == "trigger":
            if not health_sync.trigger_async():
                print("未能触发 Mac 快捷指令；请先完成 Apple 健康同步的一次性配置。")
                return 1
        print(health_sync.status_text())
        return 0
    if args.cmd in ("on", "off"):
        cfg = load_config()
        cfg["enabled"] = args.cmd == "on"
        save_config(cfg)
        print(f"Vibe Crunch {'已开启' if cfg['enabled'] else '已关闭'}。")
        return 0
    if args.cmd == "set":
        if args.value < 0 or (args.key in ("daily-goal", "daily-max") and args.value < 1):
            parser.error("数值必须为正数")
        cfg = load_config()
        if args.key == "cooldown":
            cfg["cooldown_min"] = args.value
        else:
            cfg["daily_goal"] = args.value
        save_config(cfg)
        print(status_text())
        return 0
    if args.cmd in ("done", "skip", "rest"):
        return _resolve_current(args.cmd)
    if args.cmd == "now":
        offer = prepare_offer("manual", force=True)
        if not offer:
            print("Vibe Crunch 当前已关闭。")
            return 1
        spawn_prompt(offer)
        print("已弹出：" + _describe_display_offer(offer))
        return 0
    if args.cmd == "prompt":
        return prompt_offer(args.offer_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())