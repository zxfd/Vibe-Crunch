import ast
import copy
import datetime as dt
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from workout_gate import lean_plan as lean, lean_ui
from workout_gate.micro_plan import default_micro_config, plan_offer, apply_action, swap_pending_offer


def ts(day=0, hour=15, minute=0):
    return (dt.datetime(2026, 9, 10, hour, minute) + dt.timedelta(days=day)).timestamp()


class LeanPlanTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {"micro": {**default_micro_config(), "program": "lean"}}
        self.state = {"lean": {"start_date": "2026-09-10"}}

    def offer(self, day=0, hour=15, minute=0, force=False):
        return plan_offer(self.cfg, self.state, now=ts(day, hour, minute), force=force)

    def finish(self, offer, day=0, hour=15, minute=1, feedback="good", action="done"):
        return apply_action(self.state, offer["id"], action, ts(day, hour, minute), feedback)

    def test_opt_in_does_not_change_legacy_default(self):
        self.assertNotEqual(default_micro_config().get("program"), "lean")

    def test_intro_has_one_set_and_six_distinct_movements(self):
        names = []
        for hour in range(15, 21):
            offer = self.offer(hour=hour)
            self.assertEqual(offer["sets"], 1)
            names.append(offer["exercise"])
            self.finish(offer, hour=hour)
        self.assertEqual(names, list(lean.ORDER))
        self.assertIsNone(self.offer(hour=22, force=True))
        self.assertEqual(sum(r["sets"] for r in self.state["lean"]["history"]), 6)

    def test_three_strength_days_per_week(self):
        self.assertEqual([d for d in range(7) if lean.is_strength_day(self.state, ts(d))], [0, 2, 4])

    def test_recovery_is_not_strength_and_has_daily_cap(self):
        offer = self.offer(day=1)
        self.assertEqual(offer["kind"], "recovery")
        self.finish(offer, day=1)
        self.assertEqual(self.state["lean"]["history"][-1]["sets"], 0)
        self.assertIsNone(self.offer(day=1, hour=16, force=True))

    def test_automatic_quiet_hours(self):
        for hour in (0, 10, 13, 23):
            self.assertIsNone(self.offer(hour=hour))
        self.assertIsNotNone(self.offer(hour=14))

    def test_manual_can_bypass_quiet_hours_not_pending(self):
        self.assertIsNotNone(self.offer(hour=10, force=True))
        self.assertIsNone(self.offer(hour=10, minute=1, force=True))

    def test_rest_cannot_be_bypassed_by_manual_now(self):
        offer = self.offer()
        self.finish(offer, action="rest", feedback=None)
        self.assertIsNone(self.offer(hour=17, force=True))

    def test_exact_48_hour_guard(self):
        offer = self.offer(hour=20)
        self.finish(offer, hour=20)
        self.assertNotIn("pushups", lean.eligible_exercises(self.state, ts(2, 20)))
        self.assertIn("pushups", lean.eligible_exercises(self.state, ts(2, 20, 1)))

    def test_hard_is_not_completed_but_still_requires_recovery(self):
        offer = self.offer()
        self.finish(offer, feedback="hard")
        self.assertEqual(self.state["micro_completed_today"], 0)
        self.assertEqual(self.state["lean"]["history"][-1]["sets"], 0)
        self.assertNotIn("pushups", lean.eligible_exercises(self.state, ts(0, 16)))

    def test_skip_does_not_consume_training_volume(self):
        offer = self.offer()
        self.finish(offer, action="skip", feedback=None)
        self.assertEqual(self.state["micro_completed_today"], 0)
        self.assertIn("pushups", lean.eligible_exercises(self.state, ts(0, 16)))

    def test_swap_preserves_id_time_cooldown_and_counts(self):
        offer = self.offer()
        before = copy.deepcopy(self.state)
        swapped = swap_pending_offer(self.cfg, self.state, offer["id"], now=ts(0, 15, 2))
        self.assertEqual(swapped["exercise"], "band_rows")
        for key in ("id", "created_ts", "day"):
            self.assertEqual(swapped[key], before["micro_pending"][key])
        for key in ("micro_last_offer_ts", "micro_auto_offers_today", "micro_completed_today"):
            self.assertEqual(self.state[key], before[key])

    def test_swap_cannot_bring_back_completed_exercise(self):
        offer = self.offer()
        self.finish(offer)
        offer = self.offer(hour=16)
        for _ in range(12):
            swapped = swap_pending_offer(self.cfg, self.state, offer["id"], now=ts(0, 16, 1))
            self.assertNotEqual(swapped["exercise"], "pushups")

    def test_two_easy_sessions_add_only_one_rep(self):
        for day, hour in ((0, 15), (2, 16)):
            self.state["lean_rotation"] = 0
            offer = self.offer(day=day, hour=hour)
            self.finish(offer, day=day, hour=hour, feedback="easy")
        self.assertEqual(self.state["lean"]["reps"]["pushups"], 7)

    def test_reps_are_capped(self):
        self.state["lean"]["reps"] = {"pushups": 12}
        self.state["lean"]["easy_streak"] = {"pushups": 1}
        self.finish(self.offer(), feedback="easy")
        self.assertEqual(self.state["lean"]["reps"]["pushups"], 12)

    def test_hard_reduces_target(self):
        self.state["lean"]["reps"] = {"pushups": 9}
        self.finish(self.offer(), feedback="hard")
        self.assertEqual(self.state["lean"]["reps"]["pushups"], 7)

    def test_missing_feedback_does_not_raise_sets_or_reps(self):
        self.finish(self.offer(), feedback=None)
        self.state["lean_rotation"] = 0
        offer = self.offer(day=7)
        self.assertEqual((offer["sets"], offer["reps"]), (1, 6))

    def test_week_two_requires_two_positive_reports(self):
        for day, hour in ((0, 15), (2, 16)):
            self.state["lean_rotation"] = 0
            self.finish(self.offer(day, hour), day, hour)
        self.state["lean_rotation"] = 0
        self.assertEqual(self.offer(day=7)["sets"], 2)

    def test_pain_pauses_without_false_completion(self):
        offer = self.offer()
        self.finish(offer, feedback="pain")
        self.assertEqual(self.state["micro_completed_today"], 0)
        self.assertIn("pushups", self.state["lean"]["blocked"])
        self.assertIsNone(self.offer(hour=16, force=True))
        self.assertNotIn("pushups", lean.eligible_exercises(self.state, ts(2)))

    def test_resume_does_not_cancel_rest_or_reuse_old_positive_reports(self):
        for day, hour in ((0, 15), (2, 16)):
            self.state["lean_rotation"] = 0
            self.finish(self.offer(day, hour), day, hour)
        self.state["lean_rotation"] = 0
        self.finish(self.offer(day=4, hour=17), day=4, hour=17, feedback="pain")
        lean.resume_exercise(self.state, "pushups")
        self.assertIsNone(self.offer(day=4, hour=18, force=True))
        self.state["lean_rotation"] = 0
        self.assertEqual(self.offer(day=7)["sets"], 1)

    def test_blocked_recovery_does_not_reappear(self):
        offer = self.offer(day=1)
        self.finish(offer, day=1, feedback="pain")
        self.assertEqual(lean.eligible_exercises(self.state, ts(3)), [])

    def test_stale_previous_day_cannot_be_completed(self):
        offer = self.offer()
        self.assertIsNone(self.finish(offer, day=1))
        self.assertEqual(self.state["lean"]["history"], [])

    def test_action_is_idempotent(self):
        offer = self.offer()
        self.finish(offer)
        self.assertIsNone(self.finish(offer))
        self.assertEqual(len(self.state["lean"]["history"]), 1)

    def test_wrong_offer_id_cannot_change_state(self):
        self.offer()
        before = copy.deepcopy(self.state)
        self.assertIsNone(apply_action(self.state, "wrong", "done", ts()))
        self.assertEqual(self.state, before)

    def test_report_is_read_only_and_separates_volume(self):
        self.finish(self.offer())
        self.finish(self.offer(day=1), day=1)
        before = copy.deepcopy(self.state)
        text = lean.report_text(self.state, ts(1, 18))
        self.assertIn("力量组数 1，恢复卡片 1", text)
        self.assertEqual(self.state, before)

    def test_report_does_not_activate_empty_state(self):
        state = {}
        lean.report_text(state, ts())
        self.assertEqual(state, {})

    def test_disabled_program_stays_off_even_manually(self):
        self.cfg["micro"]["enabled"] = False
        self.assertIsNone(self.offer(force=True))

    def test_all_blocked_strength_days_never_fall_back_to_unsafe_exercise(self):
        self.state["lean"]["blocked"] = list(lean.ORDER)
        self.assertIsNone(self.offer(force=True))

    def test_timeout_clears_pending_and_restarts_cooldown_on_return(self):
        offer = self.offer()
        now = offer["created_ts"]
        apply_action(self.state, offer["id"], "timeout", now=now + 1)
        self.assertIsNone(self.state["micro_pending"])
        self.assertTrue(self.state["micro_return_pending"])
        self.assertEqual(self.state["micro_completed_today"], 0)
        self.assertIsNone(plan_offer(self.cfg, self.state, now=now + 3600))
        self.assertFalse(self.state.get("micro_return_pending", False))
        self.assertEqual(self.state["micro_last_offer_ts"], now + 3600)

    def test_invalid_feedback_is_rejected_without_clearing_pending(self):
        offer = self.offer()
        with self.assertRaises(ValueError):
            self.finish(offer, feedback="invented")
        self.assertEqual(self.state["micro_pending"]["id"], offer["id"])


class LeanUiTests(unittest.TestCase):
    def test_dynamic_prescription_is_not_replaced_by_legacy_sets(self):
        # Compile the real presentation function without importing unrelated webcam code.
        source = Path(__file__).resolve().parents[1] / "workout_gate" / "micro.py"
        tree = ast.parse(source.read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_display_offer")
        namespace = {"MICRO_EXERCISES": {"pushups": {"sets": 2, "target": "8–12 次"}}}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), "exec"), namespace)
        offer = dict(program="lean", exercise="pushups", sets=1, target="6 次/组")
        self.assertEqual(namespace["_display_offer"](offer), offer)

    def test_message_contains_warmup_and_safety_without_legacy_duration_promise(self):
        state = {"lean": {"start_date": "2026-09-10"}}
        offer = lean.plan_offer({"enabled": True}, state, "test", ts())
        text = lean_ui.dialog_message(offer)
        self.assertIn("1 组", text)
        self.assertIn("不憋气", text)
        self.assertNotIn("预计 2–4 分钟", text)

    def test_mac_feedback_maps_all_buttons(self):
        for index, (expected, _) in enumerate(lean_ui.CHOICES):
            proc = subprocess.CompletedProcess([], 0, str(1000 + index), "")
            with patch.dict("sys.modules", {"tkinter": None}), patch.object(lean_ui.sys, "platform", "darwin"), patch.object(lean_ui.subprocess, "run", return_value=proc):
                self.assertEqual(lean_ui.feedback_dialog(), expected)

    def test_feedback_failure_never_defaults_to_success(self):
        for output in ("", "wrong", "9999"):
            proc = subprocess.CompletedProcess([], 1, output, "")
            with patch.dict("sys.modules", {"tkinter": None}), patch.object(lean_ui.sys, "platform", "darwin"), patch.object(lean_ui.subprocess, "run", return_value=proc):
                self.assertIsNone(lean_ui.feedback_dialog())


if __name__ == "__main__":
    unittest.main()
