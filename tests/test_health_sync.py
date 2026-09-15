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
        self.assertEqual(event["duration_seconds"], 60)

        event = health_sync.build_completion_event(self.offer("walk"), completed_ts=1060.0)
        self.assertEqual(event["workout_type"], "walking")
        self.assertEqual(event["signal_focus"], "Vibe Sync Walk")
        self.assertEqual(event["duration_seconds"], 120)

        event = health_sync.build_completion_event(self.offer("meditation"), completed_ts=1150.0)
        self.assertEqual(event["workout_type"], "mind_and_body")
        self.assertEqual(event["shortcuts_workout_type"], "Mind and Body")
        self.assertEqual(event["signal_focus"], "Vibe Sync Mindfulness")
        self.assertEqual(event["duration_seconds"], 150)

        self.assertEqual(
            set(event),
            {
                "schema_version",
                "source",
                "event_id",
                "exercise",
                "exercise_label",
                "target",
                "sets",
                "workout_type",
                "shortcuts_workout_type",
                "signal_focus",
                "start_at",
                "completed_at",
                "duration_seconds",
            },
        )

    def test_event_writer_is_idempotent_by_offer_id(self):
        first = health_sync.enqueue_completion(self.offer(), completed_ts=1030.0)
        second = health_sync.enqueue_completion(self.offer(target="updated"), completed_ts=1040.0)
        self.assertEqual(first, second)
        self.assertEqual(health_sync.event_count(), 1)
        data = json.loads(first.read_text())
        self.assertEqual(data["target"], "updated")

    def test_legacy_bridge_name_migrates_to_shared_shortcut(self):
        cfg_path = Path(self.tmp.name) / health_sync.CONFIG_NAME
        cfg_path.write_text(json.dumps({
            "enabled": False,
            "trigger_shortcut": health_sync.LEGACY_SHORTCUT,
        }))
        cfg = health_sync.load_config()
        self.assertEqual(cfg["trigger_shortcut"], "Vibe Crunch → Health")

    def test_event_dir_prefers_override(self):
        override = Path(self.tmp.name) / "explicit-ledger"
        os.environ["VIBE_CRUNCH_HEALTH_SYNC_DIR"] = str(override)
        with mock.patch.object(
            health_sync, "icloud_drive_root", return_value=Path(self.events.name)
        ):
            self.assertEqual(health_sync.event_dir(), override)
            self.assertIn("VIBE_CRUNCH_HEALTH_SYNC_DIR", health_sync.ledger_backend())

    def test_event_dir_uses_icloud_when_available(self):
        os.environ.pop("VIBE_CRUNCH_HEALTH_SYNC_DIR", None)
        root = Path(self.events.name)
        with mock.patch.object(health_sync, "icloud_drive_root", return_value=root):
            self.assertEqual(
                health_sync.event_dir(), root / "VibeCrunch" / "HealthSync" / "events"
            )
            self.assertEqual(health_sync.ledger_backend(), "iCloud Drive")

    def test_event_dir_falls_back_locally_without_icloud(self):
        os.environ.pop("VIBE_CRUNCH_HEALTH_SYNC_DIR", None)
        missing = Path(self.events.name) / "missing-icloud"
        with mock.patch.object(health_sync, "icloud_drive_root", return_value=missing):
            expected = Path(self.tmp.name) / "health-sync" / "events"
            self.assertEqual(health_sync.event_dir(), expected)
            self.assertEqual(health_sync.ledger_backend(), "本地 fallback")
            self.assertTrue(health_sync.ledger_writable())

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
            self.assertTrue(health_sync.trigger_async(event_path, "Vibe Crunch → Health"))
        self.assertEqual(
            popen.call_args.args[0],
            [
                "/usr/bin/shortcuts",
                "run",
                "Vibe Crunch → Health",
                "-i",
                str(event_path),
            ],
        )
        self.assertTrue(popen.call_args.kwargs["start_new_session"])

    def test_shortcut_detection_matches_exact_name(self):
        with (
            mock.patch.object(health_sync.sys, "platform", "darwin"),
            mock.patch.object(
                health_sync.subprocess,
                "run",
                return_value=mock.Mock(
                    returncode=0,
                    stdout="Another Shortcut\nVibe Crunch → Health\n",
                ),
            ),
        ):
            self.assertTrue(health_sync.shortcut_available())
            self.assertFalse(health_sync.shortcut_available("Missing Shortcut"))

    def test_bridge_ready_requires_macos_writable_ledger_and_shortcut(self):
        with (
            mock.patch.object(health_sync.sys, "platform", "darwin"),
            mock.patch.object(health_sync, "ledger_writable", return_value=True),
            mock.patch.object(health_sync, "shortcut_available", return_value=True),
        ):
            self.assertTrue(health_sync.bridge_ready())

        with (
            mock.patch.object(health_sync.sys, "platform", "darwin"),
            mock.patch.object(health_sync, "ledger_writable", return_value=True),
            mock.patch.object(health_sync, "shortcut_available", return_value=False),
        ):
            self.assertFalse(health_sync.bridge_ready())

        with mock.patch.object(health_sync.sys, "platform", "linux"):
            self.assertFalse(health_sync.bridge_ready())

    def test_bridge_stays_ready_with_local_fallback(self):
        os.environ.pop("VIBE_CRUNCH_HEALTH_SYNC_DIR", None)
        with (
            mock.patch.object(health_sync.sys, "platform", "darwin"),
            mock.patch.object(
                health_sync,
                "icloud_drive_root",
                return_value=Path(self.events.name) / "missing-icloud",
            ),
            mock.patch.object(health_sync, "shortcut_available", return_value=True),
        ):
            self.assertTrue(health_sync.bridge_ready())

    def test_status_reports_event_store_and_bridge_state(self):
        with (
            mock.patch.object(health_sync.sys, "platform", "darwin"),
            mock.patch.object(health_sync, "ledger_writable", return_value=True),
            mock.patch.object(health_sync, "shortcut_available", return_value=True),
        ):
            text = health_sync.status_text()
        self.assertIn("Ledger：显式目录（VIBE_CRUNCH_HEALTH_SYNC_DIR）", text)
        self.assertIn("账本写入：可用", text)
        self.assertIn("Mac/iPhone 共用快捷指令：Vibe Crunch → Health", text)
        self.assertIn("快捷指令检测：已找到", text)
        self.assertIn("Mac 端桥接：已就绪", text)

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

        self._put_pending("rest-1")
        with mock.patch.object(micro.health_sync, "sync_completion") as sync:
            rested = micro.resolve_offer("rest-1", "rest")
        self.assertIsNotNone(rested)
        sync.assert_not_called()

        self._put_pending("swap-1")
        with mock.patch.object(micro.health_sync, "sync_completion") as sync:
            swapped = micro.swap_offer("swap-1")
        self.assertIsNotNone(swapped)
        sync.assert_not_called()

        self._put_pending("timeout-1")
        with mock.patch.object(micro.health_sync, "sync_completion") as sync:
            timed_out = micro.resolve_offer("timeout-1", "timeout")
        self.assertIsNotNone(timed_out)
        sync.assert_not_called()

    def test_health_failure_does_not_rollback_local_completion(self):
        self._put_pending("fail-open-1")
        with mock.patch.object(
            micro.health_sync, "sync_completion", side_effect=OSError("ledger unavailable")
        ):
            done = micro.resolve_offer("fail-open-1", "done")
        self.assertIsNotNone(done)
        self.assertEqual(micro.load_state()["micro_completed_today"], 1)

    def test_done_and_timeout_race_only_records_the_first_resolution(self):
        self._put_pending("done-first")
        with mock.patch.object(micro.health_sync, "sync_completion") as sync:
            self.assertIsNotNone(micro.resolve_offer("done-first", "done"))
            self.assertIsNone(micro.resolve_offer("done-first", "timeout"))
        sync.assert_called_once()
        stats = micro.load_stats()
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["timed_out"], 0)

        self._put_pending("timeout-first")
        with mock.patch.object(micro.health_sync, "sync_completion") as sync:
            self.assertIsNotNone(micro.resolve_offer("timeout-first", "timeout"))
            self.assertIsNone(micro.resolve_offer("timeout-first", "done"))
        sync.assert_not_called()
        stats = micro.load_stats()
        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["timed_out"], 1)


if __name__ == "__main__":
    unittest.main()
