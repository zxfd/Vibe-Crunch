import datetime
import unittest

from workout_gate.micro_plan import (
    apply_action,
    default_micro_config,
    plan_offer,
    swap_pending_offer,
)


def ts(y, m, d, hh=12, mm=0):
    return datetime.datetime(y, m, d, hh, mm).timestamp()


class MicroPlanTests(unittest.TestCase):
    def config(self):
        return {"micro": {**default_micro_config(), "enabled": True}}

    def test_rotates_after_cooldown(self):
        cfg, st = self.config(), {}
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        self.assertEqual(first["exercise"], "pushups")
        apply_action(st, first["id"], "done", now=ts(2026, 8, 21, 12, 2))
        self.assertIsNone(plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 20)))
        second = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 31))
        self.assertEqual(second["exercise"], "band_rows")

    def test_skip_does_not_consume_daily_goal(self):
        cfg, st = self.config(), {}
        cfg["micro"]["daily_goal"] = 1
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        apply_action(st, first["id"], "skip", now=ts(2026, 8, 21, 12, 1))
        self.assertEqual(st["micro_completed_today"], 0)
        second = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 31))
        self.assertIsNotNone(second)

    def test_swap_reuses_pending_offer_without_consuming_goal(self):
        cfg, st = self.config(), {}
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        offer_id = first["id"]
        created_ts = first["created_ts"]
        auto_offers = st["micro_auto_offers_today"]
        last_offer_ts = st["micro_last_offer_ts"]

        swapped = swap_pending_offer(cfg, st, offer_id)

        self.assertEqual(swapped["id"], offer_id)
        self.assertEqual(swapped["exercise"], "band_rows")
        self.assertEqual(swapped["created_ts"], created_ts)
        self.assertEqual(st["micro_completed_today"], 0)
        self.assertEqual(st["micro_auto_offers_today"], auto_offers)
        self.assertEqual(st["micro_last_offer_ts"], last_offer_ts)

    def test_repeated_swap_advances_rotation(self):
        cfg, st = self.config(), {}
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        swapped = swap_pending_offer(cfg, st, first["id"])
        self.assertEqual(swapped["exercise"], "band_rows")
        swapped = swap_pending_offer(cfg, st, first["id"])
        self.assertEqual(swapped["exercise"], "chair_squats")

    def test_completed_goal_stops_automatic_reminders(self):
        cfg, st = self.config(), {}
        cfg["micro"]["daily_goal"] = 2
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        apply_action(st, first["id"], "done", now=ts(2026, 8, 21, 12, 1))
        second = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 31))
        apply_action(st, second["id"], "done", now=ts(2026, 8, 21, 12, 32))
        self.assertEqual(st["micro_completed_today"], 2)
        self.assertIsNone(plan_offer(cfg, st, now=ts(2026, 8, 21, 13, 2)))

    def test_rest_suppresses_until_next_day(self):
        cfg, st = self.config(), {}
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        apply_action(st, first["id"], "rest", now=ts(2026, 8, 21, 12, 1))
        self.assertIsNone(plan_offer(cfg, st, now=ts(2026, 8, 21, 18, 0)))
        self.assertIsNotNone(plan_offer(cfg, st, now=ts(2026, 8, 22, 12, 0)))

    def test_pending_offer_prevents_dialog_spam(self):
        cfg, st = self.config(), {}
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        self.assertIsNotNone(first)
        self.assertIsNone(plan_offer(cfg, st, now=ts(2026, 8, 21, 13, 0)))

    def test_stale_pending_offer_expires(self):
        cfg, st = self.config(), {}
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        self.assertIsNotNone(first)
        second = plan_offer(cfg, st, now=ts(2026, 8, 21, 13, 31))
        self.assertIsNotNone(second)
        self.assertEqual(second["exercise"], "band_rows")

    def test_force_bypasses_goal_and_counts_when_completed(self):
        cfg, st = self.config(), {}
        cfg["micro"]["daily_goal"] = 1
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        apply_action(st, first["id"], "done", now=ts(2026, 8, 21, 12, 1))
        self.assertIsNone(plan_offer(cfg, st, now=ts(2026, 8, 21, 13, 0)))

        forced = plan_offer(cfg, st, now=ts(2026, 8, 21, 13, 1), force=True)
        self.assertIsNotNone(forced)
        self.assertEqual(st["micro_auto_offers_today"], 1)
        apply_action(st, forced["id"], "done", now=ts(2026, 8, 21, 13, 2))
        self.assertEqual(st["micro_completed_today"], 2)
        self.assertIsNone(plan_offer(cfg, st, now=ts(2026, 8, 21, 14, 0)))

    def test_daily_counters_reset_on_new_day(self):
        cfg, st = self.config(), {}
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        apply_action(st, first["id"], "done", now=ts(2026, 8, 21, 12, 1))
        self.assertEqual(st["micro_completed_today"], 1)
        second = plan_offer(cfg, st, now=ts(2026, 8, 22, 12, 0))
        self.assertIsNotNone(second)
        self.assertEqual(st["micro_completed_today"], 0)
        self.assertEqual(st["micro_auto_offers_today"], 1)


if __name__ == "__main__":
    unittest.main()
