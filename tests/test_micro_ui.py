import subprocess
import sys
import types
import unittest
from unittest.mock import call, patch

from workout_gate import micro


class MicroUiTests(unittest.TestCase):
    @staticmethod
    def fake_tk(button_first=None):
        buttons = {}

        class Widget:
            def __init__(self, *args, **kwargs):
                text = kwargs.get("text")
                if text:
                    buttons[text] = kwargs.get("command")

            def pack(self, *args, **kwargs):
                return None

        class Root(Widget):
            def __init__(self):
                super().__init__()
                self.after_ms = None
                self.after_callback = None
                self.destroy_count = 0

            def title(self, *args):
                return None

            def attributes(self, *args):
                return None

            def resizable(self, *args):
                return None

            def configure(self, **kwargs):
                return None

            def protocol(self, *args):
                return None

            def update_idletasks(self):
                return None

            def winfo_reqwidth(self):
                return 640

            def winfo_reqheight(self):
                return 480

            def winfo_screenwidth(self):
                return 1920

            def winfo_screenheight(self):
                return 1080

            def geometry(self, *args):
                return None

            def lift(self):
                return None

            def focus_force(self):
                return None

            def after(self, ms, callback):
                self.after_ms = ms
                self.after_callback = callback

            def destroy(self):
                self.destroy_count += 1

            def mainloop(self):
                if button_first:
                    buttons[button_first]()
                self.after_callback()

        root = Root()
        module = types.SimpleNamespace(Tk=lambda: root, Frame=Widget, Button=Widget)
        return module, root

    def test_mac_dialog_maps_third_button_to_swap(self):
        proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="1002\n", stderr="")
        with patch.object(micro.subprocess, "run", return_value=proc) as run:
            action = micro._mac_dialog(
                {"exercise": "pushups", "source": "codex"}, timeout_s=900
            )

        self.assertEqual(action, "swap")
        args = run.call_args.args[0]
        self.assertEqual(args[:4], ["osascript", "-l", "JavaScript", "-e"])
        self.assertIn("换一个", args[4])
        self.assertEqual(run.call_args.kwargs["timeout"], 900)

    def test_mac_dialog_timeout_is_distinct_from_skip(self):
        with patch.object(
            micro.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd=["osascript"], timeout=0.01),
        ):
            action = micro._mac_dialog(
                {"exercise": "meditation", "source": "codex"}, timeout_s=0.01
            )

        self.assertEqual(action, "timeout")

    def test_meditation_dialog_uses_activity_neutral_copy(self):
        text = micro._dialog_message({"exercise": "meditation", "source": "codex"})

        self.assertIn("本轮：正念冥想", text)
        self.assertIn("活动要点", text)
        self.assertNotIn("卷一下腹", text)
        self.assertNotIn("不做到力竭", text)
        self.assertNotIn("15 分钟", text)

    def test_tk_dialog_registers_hidden_timeout_and_destroys_once(self):
        fake_tk, root = self.fake_tk()
        with patch.dict(sys.modules, {"tkinter": fake_tk}):
            action = micro._tk_dialog({"exercise": "meditation"}, timeout_s=900)

        self.assertEqual(action, "timeout")
        self.assertEqual(root.after_ms, 900_000)
        self.assertEqual(root.destroy_count, 1)

    def test_tk_button_wins_race_with_timeout_callback(self):
        fake_tk, root = self.fake_tk(button_first="完成了")
        with patch.dict(sys.modules, {"tkinter": fake_tk}):
            action = micro._tk_dialog({"exercise": "meditation"}, timeout_s=900)

        self.assertEqual(action, "done")
        self.assertEqual(root.destroy_count, 1)

    def test_prompt_reopens_after_swap_without_resolving_it(self):
        first = {"id": "offer-1", "exercise": "band_rows"}
        second = {"id": "offer-1", "exercise": "chair_squats"}
        with (
            patch.object(micro.sys, "platform", "darwin"),
            patch.object(micro, "_pending", side_effect=[first, second]),
            patch.object(micro, "_tk_dialog", side_effect=["swap", "done"]),
            patch.object(micro, "_mac_dialog") as mac_dialog,
            patch.object(micro, "swap_offer", return_value=second) as swap,
            patch.object(micro, "resolve_offer") as resolve,
        ):
            result = micro.prompt_offer("offer-1", timeout_s=900)

        self.assertEqual(result, 0)
        self.assertEqual(swap.call_args_list, [call("offer-1")])
        self.assertEqual(resolve.call_args_list, [call("offer-1", "done")])
        mac_dialog.assert_not_called()

    def test_swap_restarts_the_hidden_inactivity_window(self):
        first = {"id": "offer-1", "exercise": "pushups"}
        second = {"id": "offer-1", "exercise": "meditation"}
        with (
            patch.object(micro, "_pending", side_effect=[first, second]),
            patch.object(micro, "_tk_dialog", side_effect=["swap", "done"]) as dialog,
            patch.object(micro, "swap_offer", return_value=second),
            patch.object(micro, "resolve_offer"),
        ):
            micro.prompt_offer("offer-1", timeout_s=900)

        first_remaining = dialog.call_args_list[0].args[1]
        second_remaining = dialog.call_args_list[1].args[1]
        self.assertEqual(first_remaining, 900)
        self.assertEqual(second_remaining, 900)

    def test_prompt_falls_back_to_mac_dialog_when_tk_is_unavailable(self):
        offer = {"id": "offer-1", "exercise": "band_rows"}
        with (
            patch.object(micro.sys, "platform", "darwin"),
            patch.object(micro, "_pending", return_value=offer),
            patch.object(micro, "_tk_dialog", return_value=None),
            patch.object(micro, "_mac_dialog", return_value="done") as mac_dialog,
            patch.object(micro, "resolve_offer") as resolve,
        ):
            result = micro.prompt_offer("offer-1", timeout_s=900)

        self.assertEqual(result, 0)
        self.assertEqual(mac_dialog.call_args.args[0], offer)
        self.assertGreater(mac_dialog.call_args.args[1], 0)
        resolve.assert_called_once_with("offer-1", "done")

    def test_prompt_resolves_hidden_countdown_as_timeout(self):
        offer = {"id": "offer-1", "exercise": "meditation"}
        with (
            patch.object(micro, "_pending", return_value=offer),
            patch.object(micro, "_tk_dialog", return_value="timeout"),
            patch.object(micro, "resolve_offer") as resolve,
        ):
            result = micro.prompt_offer("offer-1", timeout_s=900)

        self.assertEqual(result, 0)
        resolve.assert_called_once_with("offer-1", "timeout")

    def test_spawn_prompt_prefers_system_python_on_macos(self):
        with (
            patch.object(micro.sys, "platform", "darwin"),
            patch.object(micro.os, "access", return_value=True),
            patch.object(micro.subprocess, "Popen") as popen,
        ):
            micro.spawn_prompt({"id": "offer-1"})

        args = popen.call_args.args[0]
        self.assertEqual(args[:5], ["/usr/bin/python3", "-m", "workout_gate.micro", "prompt", "offer-1"])
        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_spawn_prompt_keeps_current_python_without_system_python(self):
        with (
            patch.object(micro.sys, "platform", "darwin"),
            patch.object(micro.sys, "executable", "/custom/python"),
            patch.object(micro.os, "access", return_value=False),
            patch.object(micro.subprocess, "Popen") as popen,
        ):
            micro.spawn_prompt({"id": "offer-1"})

        self.assertEqual(popen.call_args.args[0][0], "/custom/python")


if __name__ == "__main__":
    unittest.main()
