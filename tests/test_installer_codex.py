"""Codex global install: surgical edits to ~/.codex/hooks.json, same care as
the Claude settings.json path (preserve, backup, atomic, remove only ours)."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from workout_gate import installer


class CodexInstallerTest(unittest.TestCase):
    """Runs against a fake HOME so the user's real ~/.codex is never touched."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_home = os.environ["HOME"]
        os.environ["HOME"] = self.tmp.name
        self.path = Path(self.tmp.name) / ".codex" / "hooks.json"
        self.config_path = self.path.parent / "config.toml"

    def tearDown(self):
        os.environ["HOME"] = self.old_home
        self.tmp.cleanup()

    def test_enable_creates_hook(self):
        msg = installer.enable_codex()
        data = json.loads(self.path.read_text())
        entry = data["hooks"]["UserPromptSubmit"][0]["hooks"][0]
        self.assertIn("gate.sh", entry["command"])
        self.assertIn("WORKOUT_GATE_SOURCE=codex", entry["command"])  # speaker tag
        self.assertEqual(entry["timeout"], 300)
        self.assertTrue(installer.is_codex_installed())
        self.assertIn("/hooks", msg)  # trust-review reminder is surfaced

    def test_enable_is_idempotent(self):
        installer.enable_codex()
        installer.enable_codex()
        data = json.loads(self.path.read_text())
        self.assertEqual(len(data["hooks"]["UserPromptSubmit"]), 1)

    def test_stable_micro_launcher_is_recognized_without_adding_legacy_duplicate(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "hooks": {"UserPromptSubmit": [{"hooks": [{
                "type": "command",
                "command": "/Users/test/.local/bin/vibe-crunch-hook",
            }]}]},
        }))

        installer.enable_codex()

        data = json.loads(self.path.read_text())
        self.assertEqual(len(data["hooks"]["UserPromptSubmit"]), 1)
        self.assertTrue(installer.is_codex_installed())

    def test_enable_preserves_existing_and_backs_up(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "hooks": {"UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "echo hi"}]}]}}))
        installer.enable_codex()
        data = json.loads(self.path.read_text())
        self.assertEqual(len(data["hooks"]["UserPromptSubmit"]), 2)
        self.assertEqual(data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"], "echo hi")
        self.assertTrue((self.path.parent / "hooks.json.workout-gate.bak").exists())

    def test_disable_removes_only_ours(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "hooks": {"UserPromptSubmit": [
                {"hooks": [{"type": "command", "command": "echo hi"}]}]}}))
        installer.enable_codex()
        installer.disable_codex()
        data = json.loads(self.path.read_text())
        self.assertEqual(len(data["hooks"]["UserPromptSubmit"]), 1)
        self.assertEqual(data["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"], "echo hi")
        self.assertFalse(installer.is_codex_installed())

    def test_disable_cleans_empty_containers(self):
        installer.enable_codex()
        installer.disable_codex()
        data = json.loads(self.path.read_text())
        self.assertNotIn("hooks", data)

    def test_status_strings(self):
        self.assertIn("not installed", installer.codex_status())
        installer.enable_codex()
        self.assertIn("INSTALLED", installer.codex_status())

    def test_status_reports_persisted_codex_hook_disable(self):
        installer.enable_codex()
        state_id = f"{self.path}:user_prompt_submit:0:0"
        self.config_path.write_text(
            f'[hooks.state."{state_id}"]\n'
            'trusted_hash = "sha256:test"\n'
            'enabled = false\n'
        )

        self.assertEqual(installer.codex_hook_runtime_state(), "disabled")
        self.assertIn("INSTALLED BUT DISABLED", installer.codex_status())

    def test_status_treats_missing_enable_switch_as_configured(self):
        installer.enable_codex()
        state_id = f"{self.path}:user_prompt_submit:0:0"
        self.config_path.write_text(
            f'[hooks.state."{state_id}"]\n'
            'trusted_hash = "sha256:test"\n'
        )

        self.assertEqual(installer.codex_hook_runtime_state(), "configured")

    def test_disable_when_never_installed(self):
        installer.disable_codex()  # must not raise
        self.assertFalse(installer.is_codex_installed())


if __name__ == "__main__":
    unittest.main()
