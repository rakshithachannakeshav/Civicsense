import json
import tempfile
from pathlib import Path
from unittest import TestCase, mock

import agents

from .helpers import OfflineAgentsMixin


class CosineTests(TestCase):
    def test_identical_vectors_score_one(self):
        self.assertAlmostEqual(agents.cosine([1, 2, 3], [1, 2, 3]), 1.0)

    def test_orthogonal_vectors_score_zero(self):
        self.assertAlmostEqual(agents.cosine([1, 0], [0, 1]), 0.0)

    def test_zero_vector_is_safe(self):
        self.assertEqual(agents.cosine([0, 0], [1, 1]), 0.0)


class RulesFileTests(TestCase):
    def test_shipped_rules_are_valid(self):
        rules = agents.load_rules()
        self.assertGreaterEqual(len(rules), 1)
        categories = {r["category"] for r in rules}
        self.assertTrue({"road_damage", "garbage", "streetlight", "water_leak"} <= categories)

    def test_missing_field_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            path.write_text(json.dumps({"rules": [{"category": "garbage"}]}))
            with self.assertRaisesRegex(ValueError, "missing"):
                agents.load_rules(path)


class ClassifierTests(OfflineAgentsMixin, TestCase):
    def test_unclear_text_asks_for_details(self):
        result = agents.process_complaint("something is wrong here", "unknown")
        self.assertEqual(result["category"], "other")
        self.assertIn("more details", result["note"])
        self.assertNotIn("letter", result)

    def test_specific_words_win_over_the_word_road(self):
        lamp = agents.process_complaint("Street lamp not working, the road is dark", "Church St")
        self.assertEqual(lamp["category"], "streetlight")
        pipe = agents.process_complaint("Burst pipe, water gushing onto the road", "12th Main")
        self.assertEqual(pipe["category"], "water_leak")
        self.assertEqual(pipe["severity"], "high")

    def test_dangerous_words_raise_severity(self):
        result = agents.process_complaint("Huge dangerous pothole near the school", "Main St")
        self.assertEqual(result["category"], "road_damage")
        self.assertEqual(result["severity"], "high")


class RouterTests(OfflineAgentsMixin, TestCase):
    def test_routes_to_a_desk_of_the_right_category(self):
        result = agents.process_complaint("Garbage not collected for four days", "5th Cross")
        self.assertEqual(result["department"], "Solid Waste Dept")
        self.assertTrue(result["letter"])
        self.assertTrue(result["rule"])

    def test_sla_is_the_smaller_of_rule_and_severity_cap(self):
        # Rule SLAs for garbage are 48 h and 72 h; a high-severity cap is 24 h.
        high = agents.router({"text": "garbage dangerous", "reason": "garbage dangerous",
                              "category": "garbage", "severity": "high", "location": "x"})
        self.assertEqual(high["sla_hours"], 24)
        # A low-severity cap is 168 h, so the rule's own SLA wins.
        low = agents.router({"text": "missed pickup", "reason": "missed pickup",
                             "category": "garbage", "severity": "low", "location": "x"})
        self.assertIn(low["sla_hours"], (48, 72))
        self.assertLess(low["sla_hours"], 168)


class DuplicateTests(TestCase):
    """The duplicate check needs BOTH issue and place similarity to be high."""

    def run_check(self, desc_vec, loc_vec, known_category="road_damage"):
        known = [{"ref": "C-1", "category": known_category,
                  "desc_vec": [1.0, 0.0], "loc_vec": [1.0, 0.0]}]
        fake = mock.Mock()
        fake.embed_query.side_effect = [desc_vec, loc_vec]
        with mock.patch.object(agents, "get_embeddings", return_value=fake):
            return agents.duplicate_check({
                "reason": "pothole", "location": "80 Feet Road",
                "category": "road_damage", "known": known,
            })

    def test_same_issue_same_place_is_duplicate(self):
        self.assertEqual(self.run_check([1.0, 0.0], [1.0, 0.0]), {"duplicate_of": "C-1"})

    def test_same_issue_different_place_is_not_duplicate(self):
        result = self.run_check([1.0, 0.0], [0.0, 1.0])
        self.assertEqual(result["duplicate_of"], "")
        self.assertIn("desc_vec", result)   # vectors are handed back to be saved

    def test_different_issue_same_place_is_not_duplicate(self):
        self.assertEqual(self.run_check([0.0, 1.0], [1.0, 0.0])["duplicate_of"], "")

    def test_different_category_is_never_duplicate(self):
        result = self.run_check([1.0, 0.0], [1.0, 0.0], known_category="garbage")
        self.assertEqual(result["duplicate_of"], "")

    def test_thresholds_are_inclusive(self):
        # Exactly at the thresholds counts as a match.
        import math
        d = [math.cos(math.acos(agents.DESC_T)), math.sin(math.acos(agents.DESC_T))]
        l = [math.cos(math.acos(agents.LOC_T)), math.sin(math.acos(agents.LOC_T))]
        self.assertEqual(self.run_check(d, l), {"duplicate_of": "C-1"})


class FollowUpGraphTests(TestCase):
    def record(self, sla=24):
        return agents.new_record("C-1", "Roads Dept", "Ward Engineer", sla)

    def run_at(self, rec, hour):
        return agents.followup_app.invoke({**rec, "now": hour})

    def test_new_complaint_is_open_and_idle(self):
        rec = self.record()
        result = self.run_at(rec, 1)
        self.assertEqual(result["status"], "open")
        self.assertEqual(result["level"], 0)

    def test_reminder_at_quarter_of_window_sent_once(self):
        rec = self.record(24)
        rec = self.run_at(rec, 18)                    # 6 h left = 25 %
        self.assertTrue(rec["reminded"])
        self.assertEqual([e["kind"] for e in rec["events"]], ["reminder"])
        rec = {k: v for k, v in rec.items() if k != "events"}
        again = self.run_at(rec, 19)
        self.assertEqual(again.get("events", []), [])  # not reminded twice

    def test_overdue_escalates_one_level(self):
        result = self.run_at(self.record(24), 24)
        self.assertEqual(result["level"], 1)
        self.assertEqual(result["due_hour"], 24 + agents.ESCALATION_WINDOW)
        self.assertEqual(result["events"][0]["kind"], "escalation")
        self.assertIn("Head of Roads Dept", result["events"][0]["to"])

    def test_full_chain_ends_critical(self):
        rec = self.record(24)
        for hour in range(0, 90, 3):
            rec = self.run_at({k: v for k, v in rec.items() if k != "events"}, hour)
        self.assertEqual(rec["status"], "critical")
        self.assertEqual(rec["level"], agents.MAX_LEVEL)
        text = "\n".join(rec["history"])
        self.assertIn("Commissioner's Office", text)
        self.assertIn("CRITICAL", text)

    def test_resolved_complaint_is_closed(self):
        rec = {**self.record(), "status": "resolved"}
        result = self.run_at(rec, 5)
        self.assertEqual(result["status"], "closed")
        self.assertEqual(result["events"][0]["kind"], "closed")

    def test_closed_and_critical_do_nothing(self):
        for status in ("closed", "critical"):
            rec = {**self.record(), "status": status}
            self.assertEqual(self.run_at(rec, 500)["history"], rec["history"])
