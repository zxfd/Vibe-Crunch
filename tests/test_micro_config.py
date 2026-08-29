import json
import os
import tempfile
import unittest
from pathlib import Path

from workout_gate import micro
from workout_gate.micro_plan import MICRO_EXERCISES


class MicroConfigMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["WORKOUT_GATE_DIR"] = self.tmp.name
        self.root = Path(self.tmp.name)

    def tearDown(self):
        os.environ.pop("WORKOUT_GATE_DIR", None)
        self.tmp.cleanup()

    def test_legacy_rotation_config_migrates_to_full_random_pool(self):
        (self.root / micro.CONFIG_NAME).write_text(json.dumps({
            "enabled": True,
            "cooldown_min": 30,
            "exercise_order": ["pushups", "band_rows", "chair_squats"],
        }))

        cfg = micro.load_config()

        self.assertNotIn("exercise_order", cfg)
        self.assertEqual(cfg["exercise_pool"], list(MICRO_EXERCISES))
        self.assertIn("walk", cfg["exercise_pool"])
        self.assertIn("wall_sit", cfg["exercise_pool"])
        self.assertIn("meditation", cfg["exercise_pool"])
        self.assertNotIn("band_rows", cfg["exercise_pool"])
        self.assertNotIn("chair_squats", cfg["exercise_pool"])

    def test_pre_meditation_default_pool_is_upgraded_without_changing_custom_pools(self):
        legacy_pool = [name for name in MICRO_EXERCISES if name != "meditation"]
        (self.root / micro.CONFIG_NAME).write_text(json.dumps({"exercise_pool": legacy_pool}))

        self.assertEqual(micro.load_config()["exercise_pool"], list(MICRO_EXERCISES))

        custom_pool = ["walk", "wall_angels"]
        (self.root / micro.CONFIG_NAME).write_text(json.dumps({"exercise_pool": custom_pool}))
        self.assertEqual(micro.load_config()["exercise_pool"], custom_pool)

    def test_legacy_rotation_state_is_removed_without_touching_other_state(self):
        (self.root / micro.STATE_NAME).write_text(json.dumps({
            "micro_rotation_index": 3,
            "micro_completed_today": 2,
            "custom_key": "keep-me",
        }))

        state = micro.load_state()
        self.assertNotIn("micro_rotation_index", state)
        self.assertEqual(state["custom_key"], "keep-me")

        micro.save_state(state)
        on_disk = json.loads((self.root / micro.STATE_NAME).read_text())
        self.assertNotIn("micro_rotation_index", on_disk)
        self.assertEqual(on_disk["custom_key"], "keep-me")

    def test_status_reports_random_pool(self):
        text = micro.status_text()
        self.assertIn("动作选择：完全随机", text)
        self.assertIn(f"{len(MICRO_EXERCISES)} 个动作", text)
        self.assertIn("弹窗无人操作：15 分钟后自动收起", text)


if __name__ == "__main__":
    unittest.main()
