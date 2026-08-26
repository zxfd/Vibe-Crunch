import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from workout_gate import health_sync, micro


class HealthSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.events = tempfile.TemporaryDirectory()
        os.environ["WORKOUT_GATE_DIR"] = self.tmp.name
        os.environ["VIBE_CRUNCH_HEALTH_SYNC_DIR"] = self.events.name

    def tearDown(self):
        os.environ.pop("WORKOUT_GATE_DIR", None)
        os.environ.pop("VIBE_CRUNCH_HEALTH_SYNC_DIR", None)
        self.events.cleanup()
        self.tmp.cleanup()

    @staticmethod
    def offer(exercise="pushups", **extra):
        out = {
            "id": "event-1",
            "exercise": exercise,
            "label": exercise,
            "sets": 1,
            "target": "test target",
            "created_ts": 1000.0,
            "day": "2026-08-27",
        }
        out.update(extra)
        return out

    def test_event_maps_exercise_to_health_category_and_focus(self):
        event = health_sync.build_completion_event(self.offer("pushups"), completed_ts=1100.0)
        self.assertEqual(event["schema_version"], "1.1")
        self.assertEqual(event["workout_type"], "functional_strength_training")
        self.assertEqual(event["shortcuts_workout_type"], "Functional Strength Training")
        self.assertEqual(event["signal_focus"], "Vibe Sync Strength")
        # Push-up elapsed time is clamped to the conservative 60-second ceiling.
        self.assertEqual(event["duration_seconds"], 60)

        event = health_sync.build_completion_event(self.offer("walk"), completed_ts=1060.0)
        self.assertEqual(event["workout_type"], "walking")
        self.assertEqual(event["signal_focus"], "Vibe Sync Walk")
        # A 2–3 minute walking snack should never be logged as a 60-second walk.
        self.assertEqual(event["duration_seconds"], 120)

    def test_event_writer_is_idempotent_by_offer_id(self):
        first = health_sync.enqueue_completion(self.offer(), completed_ts=1030.0)
        second = health_sync.enqueue_completion(self.offer(target="updated"), completed_ts=1040.0)
        self.assertEqual(first, second)
        self.assertEqual(health_sync.event_count(), 1)
        data = json.loads(first.read_text())
        self.assertEqual(data["target"], "updated")

    def test_disabled_sync_is_a_noop(self):
        health_sync.set_enabled(False)
        with mock.patch.object(health_sync, "trigger_async") as trigger:
            self.assertFalse(health_sync.sync_completion(self.offer(), completed_ts=1030.0))
        self.assertEqual(health_sync.event_count(), 0)
        trigger.assert_not_called()

    def test_enabled_sync_writes_before_triggering(self):
        health_sync.set_enabled(True)
        with mock.patch.object(health_sync, "trigger_async", return_value=True) as trigger:
            self.assertTrue(health_sync.sync_completion(self.offer(), completed_ts=1030.0))
        self.assertEqual(health_sync.event_count(), 1)
        event_path = Path(self.events.name) / "event-1.json"
        trigger.assert_called_once_with(event_path, health_sync.DEFAULT_SHORTCUT)
        self.assertTrue(event_path.exists())

    def test_mac_shortcut_receives_event_file_as_input(self):
        event_path = health_sync.enqueue_completion(self.offer(), completed_ts=1030.0)
        with (
            mock.patch.object(health_sync.sys, "platform", "darwin"),
            mock.patch.object(health_sync.subprocess, "Popen") as popen,
        ):
            self.assertTrue(health_sync.trigger_async(event_path, "Vibe Crunch Health Sync"))
        self.assertEqual(
            popen.call_args.args[0],
            [
                "/usr/bin/shortcuts",
                "run",
                "Vibe Crunch Health Sync",
                "-i",
                str(event_path),
            ],
        )
        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def _put_pending(self, offer_id="offer-1"):
        st = micro.load_state()
        st["micro_day"] = micro.store.today()
        st["micro_completed_today"] = 0
        st["micro_pending"] = {
            "id": offer_id,
            "exercise": "pushups",
            "label": "俯卧撑",
            "sets": 1,
            "target": "4–6 次",
            "created_ts": 1000.0,
            "day": micro.store.today(),
        }
        micro.save_state(st)

    def test_only_done_is_forwarded_to_health_bridge(self):
        self._put_pending("done-1")
        with mock.patch.object(micro.health_sync, "sync_completion") as sync:
            done = micro.resolve_offer("done-1", "done")
        self.assertIsNotNone(done)
        sync.assert_called_once()
        self.assertEqual(sync.call_args.args[0]["exercise"], "pushups")

        self._put_pending("skip-1")
        with mock.patch.object(micro.health_sync, "sync_completion") as sync:
            skipped = micro.resolve_offer("skip-1", "skip")
        self.assertIsNotNone(skipped)
        sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
