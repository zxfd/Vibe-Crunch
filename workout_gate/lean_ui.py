"""Optional feedback UI; runs only in the existing detached prompt process."""
from __future__ import annotations

import subprocess
import sys

CHOICES = (
    ("easy", "已完成，轻松（还可做 ≥4 次）"),
    ("good", "已完成，合适（还可做 2–3 次）"),
    ("hard", "太难 / 未做够（不记满组）"),
    ("pain", "关节疼痛 / 不适，停止"),
)


def dialog_message(offer: dict) -> str:
    strength = offer["kind"] == "strength"
    instruction = (
        "先用更轻方式试做 3–5 次；不把热身计入训练组。\n"
        "组间休息 60–90 秒，保留 2–3 次标准动作余力，不憋气。\n"
        "胸痛、头晕或关节疼痛时立即停；不要为了打卡做满。\n"
        "结束或出现不适，点「结束 / 反馈」选择真实情况。"
    ) if strength else "这是恢复活动，不计增肌组数；身体不适可以直接休息。"
    return (
        f"薄肌入门｜{'力量训练' if strength else '恢复日'}\n\n"
        f"本轮：{offer['label']}\n做 {offer['sets']} 组，{offer['target']}\n\n"
        f"动作要点：{offer['cue']}\n\n{instruction}\n\n"
        "按钮说明：\n"
        "• 结束 / 反馈：按真实完成度记录；疼痛会暂停动作\n"
        "• 换一个：换到尚可训练的动作\n"
        "• 跳过这次：不记完成、不补债\n"
        "• 今天休息：当天停止提醒，手动 now 也不强行补练"
    )


def feedback_dialog():
    if sys.platform == "darwin":
        script = r'''
ObjC.import("AppKit");
function run(argv) {
    const alert = $.NSAlert.new;
    alert.messageText = "本轮训练感觉如何？";
    alert.informativeText = "只在完成全部规定次数且无疼痛时选前两项。关闭窗口不算完成。";
    argv.forEach(function(label) { alert.addButtonWithTitle(label); });
    $.NSApplication.sharedApplication.activateIgnoringOtherApps(true);
    return alert.runModal;
}
'''
        try:
            proc = subprocess.run(
                ["osascript", "-l", "JavaScript", "-e", script, *[label for _, label in CHOICES]],
                text=True, capture_output=True, check=False,
            )
            index = int(proc.stdout.strip()) - 1000
            if proc.returncode == 0 and 0 <= index < len(CHOICES):
                return CHOICES[index][0]
        except (OSError, ValueError):
            pass
        return None
    root = None
    result = {"rating": None}
    try:
        import tkinter as tk
        root = tk.Tk()
        root.title("本轮训练感觉如何？")
        root.attributes("-topmost", True)

        def choose(rating):
            result["rating"] = rating
            root.destroy()

        for value, label in CHOICES:
            tk.Button(root, text=label, width=38,
                      command=lambda rating=value: choose(rating)).pack(padx=12, pady=6)
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.mainloop()
    except Exception:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
    return result["rating"]
