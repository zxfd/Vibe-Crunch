import importlib.util
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "hooks" / "micro_gate.py"
SPEC = importlib.util.spec_from_file_location("vibe_crunch_micro_gate", MODULE_PATH)
micro_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(micro_gate)


class MicroGateOutputTests(unittest.TestCase):
    def test_success_path_keeps_stdout_and_stderr_empty(self):
        payload = {
            "session_id": "session-1",
            "turn_id": "turn-1",
            "prompt": "inspect the repository",
            "model": "gpt-5.6",
        }
        offer = {
            "id": "offer-1",
            "exercise": "pushups",
            "label": "俯卧撑",
            "sets": 2,
            "target": "8–12 次/组",
        }
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch.object(micro_gate.sys, "stdin", io.StringIO(json.dumps(payload))),
            patch.object(micro_gate, "duplicate_invocation", return_value=False),
            patch.object(micro_gate.micro, "enabled", return_value=True),
            patch.object(micro_gate.micro, "prepare_offer", return_value=offer),
            patch.object(micro_gate.micro, "spawn_prompt"),
            patch.object(micro_gate, "log"),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            result = micro_gate.main()

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
