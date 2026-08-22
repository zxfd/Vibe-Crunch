import subprocess
import unittest
from unittest.mock import call, patch

from workout_gate import micro


class MicroUiTests(unittest.TestCase):
    def test_mac_dialog_maps_third_button_to_swap(self):
        proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="1002\n", stderr="")
        with patch.object(micro.subprocess, "run", return_value=proc) as run:
            action = micro._mac_dialog({"exercise": "pushups", "source": "codex"})

        self.assertEqual(action, "swap")
        args = run.call_args.args[0]
        self.assertEqual(args[:4], ["osascript", "-l", "JavaScript", "-e"])
        self.assertIn("换一个", args[4])

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
            result = micro.prompt_offer("offer-1")

        self.assertEqual(result, 0)
        self.assertEqual(swap.call_args_list, [call("offer-1")])
        self.assertEqual(resolve.call_args_list, [call("offer-1", "done")])
        mac_dialog.assert_not_called()

    def test_prompt_falls_back_to_mac_dialog_when_tk_is_unavailable(self):
        offer = {"id": "offer-1", "exercise": "band_rows"}
        with (
            patch.object(micro.sys, "platform", "darwin"),
            patch.object(micro, "_pending", return_value=offer),
            patch.object(micro, "_tk_dialog", return_value=None),
            patch.object(micro, "_mac_dialog", return_value="done") as mac_dialog,
            patch.object(micro, "resolve_offer") as resolve,
        ):
            result = micro.prompt_offer("offer-1")

        self.assertEqual(result, 0)
        mac_dialog.assert_called_once_with(offer)
        resolve.assert_called_once_with("offer-1", "done")

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
