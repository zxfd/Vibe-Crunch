import datetime
import unittest
from unittest.mock import patch

from workout_gate.micro_plan import (
    MICRO_EXERCISES,
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

    def test_default_pool_is_personalized_low_friction_set(self):
        pool = default_micro_config()["exercise_pool"]
        self.assertEqual(pool, list(MICRO_EXERCISES))
        self.assertIn("walk", pool)
        self.assertIn("wall_sit", pool)
        self.assertIn("plank", pool)
        self.assertNotIn("chair_squats", pool)
        self.assertNotIn("band_rows", pool)

    def test_new_offers_are_fully_random_and_can_repeat(self):
        cfg, st = self.config(), {}
        with patch("workout_gate.micro_plan.random.choice", side_effect=["walk", "walk"]):
            first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
            self.assertEqual(first["exercise"], "walk")
            apply_action(st, first["id"], "done", now=ts(2026, 8, 21, 12, 2))
            self.assertIsNone(plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 20)))
            second = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 31))
            self.assertEqual(second["exercise"], "walk")
        self.assertNotIn("micro_rotation_index", st)

    def test_configured_pool_limits_random_selection(self):
        cfg, st = self.config(), {}
        cfg["micro"]["exercise_pool"] = ["pushups", "walk", "not-real"]
        with patch("workout_gate.micro_plan.random.choice", return_value="walk") as choose:
            offer = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        self.assertEqual(offer["exercise"], "walk")
        self.assertEqual(choose.call_args.args[0], ["pushups", "walk"])

    def test_skip_does_not_consume_daily_goal(self):
        cfg, st = self.config(), {}
        cfg["micro"]["daily_goal"] = 1
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        apply_action(st, first["id"], "skip", now=ts(2026, 8, 21, 12, 1))
        self.assertEqual(st["micro_completed_today"], 0)
        second = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 31))
        self.assertIsNotNone(second)

    def test_swap_reuses_pending_offer_and_randomizes_away_from_current(self):
        cfg, st = self.config(), {}
        with patch("workout_gate.micro_plan.random.choice", return_value="pushups"):
            first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        offer_id = first["id"]
        created_ts = first["created_ts"]
        auto_offers = st["micro_auto_offers_today"]
        last_offer_ts = st["micro_last_offer_ts"]

        with patch("workout_gate.micro_plan.random.choice", return_value="walk") as choose:
            swapped = swap_pending_offer(cfg, st, offer_id)

        self.assertEqual(swapped["id"], offer_id)
        self.assertEqual(swapped["exercise"], "walk")
        self.assertNotIn("pushups", choose.call_args.args[0])
        self.assertEqual(swapped["created_ts"], created_ts)
        self.assertEqual(st["micro_completed_today"], 0)
        self.assertEqual(st["micro_auto_offers_today"], auto_offers)
        self.assertEqual(st["micro_last_offer_ts"], last_offer_ts)

    def test_single_exercise_pool_swap_keeps_same_exercise(self):
        cfg, st = self.config(), {}
        cfg["micro"]["exercise_pool"] = ["plank"]
        first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
        swapped = swap_pending_offer(cfg, st, first["id"])
        self.assertEqual(swapped["exercise"], "plank")

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

    def test_stale_pending_offer_expires_and_draws_again(self):
        cfg, st = self.config(), {}
        with patch("workout_gate.micro_plan.random.choice", side_effect=["pushups", "dead_bug"]):
            first = plan_offer(cfg, st, now=ts(2026, 8, 21, 12, 0))
            self.assertEqual(first["exercise"], "pushups")
            second = plan_offer(cfg, st, now=ts(2026, 8, 21, 13, 31))
            self.assertEqual(second["exercise"], "dead_bug")

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
