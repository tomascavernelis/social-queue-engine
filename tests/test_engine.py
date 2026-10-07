import copy
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sqe.export import ffmpeg_cmd  # noqa: E402
from sqe.history import History  # noqa: E402
from sqe.planner import plan_day  # noqa: E402
from sqe.qc import has_errors, run_qc  # noqa: E402
from sqe.util import load_json  # noqa: E402

ACC = load_json(ROOT / "config" / "accounts.json")
CAP = load_json(ROOT / "config" / "captions.json")


def fresh_hist():
    return History(Path(tempfile.mkdtemp()) / "h.jsonl")


class PlannerTest(unittest.TestCase):
    def test_plan_has_one_item_per_slot_and_passes_its_own_qc(self):
        h = fresh_hist()
        items = plan_day("2026-10-08", ACC, CAP, h)
        self.assertEqual(len(items), 8)
        self.assertFalse(has_errors(run_qc(items, ACC, h)))

    def test_exactly_one_test_per_account_per_day_and_never_in_link_slot(self):
        items = plan_day("2026-10-08", ACC, CAP, fresh_hist())
        for acct in ACC["accounts"]:
            tests = [i for i in items if i["account"] == acct["id"] and i["kind"] == "test"]
            self.assertEqual(len(tests), 1)
            self.assertNotEqual(tests[0]["time"], acct["link_slot"])

    def test_link_only_in_link_slot_and_best_winner_goes_there(self):
        items = plan_day("2026-10-08", ACC, CAP, fresh_hist())
        for i in items:
            acct = next(a for a in ACC["accounts"] if a["id"] == i["account"])
            self.assertEqual(bool(i["link"]), i["time"] == acct["link_slot"])
        a_link = next(i for i in items if i["account"] == "acct-a" and i["time"] == "19:30")
        self.assertEqual(a_link["asset"], "a-w1")

    def test_mirror_only_on_plain_subjects(self):
        h = fresh_hist()
        for d in range(1, 29):
            for i in plan_day(f"2026-10-{d:02d}", ACC, CAP, h):
                if i["variant"] and i["variant"]["mirror"]:
                    acct = next(a for a in ACC["accounts"] if a["id"] == i["account"])
                    w = next(w for w in acct["winners"] if w["id"] == i["asset"])
                    self.assertTrue(w["plain"])
                h.add([i])

    def test_captions_do_not_repeat_on_an_account_within_cooldown(self):
        h = fresh_hist()
        seen = {}
        for d in range(1, 4):  # 3 days x 3 slots = 9 captions, inside the 10-caption pool
            for i in plan_day(f"2026-10-{d:02d}", ACC, CAP, h):
                if i["account"] == "acct-a":
                    self.assertNotIn(i["caption"], seen.setdefault(i["account"], set()))
                    seen[i["account"]].add(i["caption"])
                h.add([i])

    def test_variants_rotate_instead_of_repeating(self):
        h = fresh_hist()
        used = Counter()
        for d in range(1, 8):
            for i in plan_day(f"2026-10-{d:02d}", ACC, CAP, h):
                if i["account"] == "acct-b" and i["asset"] == "b-w1":
                    used[str(i["variant"])] += 1
                h.add([i])
        self.assertLessEqual(max(used.values()), 2)


    def test_exhausted_pool_is_flagged_by_qc_not_hidden(self):
        h = fresh_hist()
        flagged = False
        for d in range(1, 8):
            items = plan_day(f"2026-10-{d:02d}", ACC, CAP, h)
            flagged |= any(i["rule"] == "caption_repeat" for i in run_qc(items, ACC, h))
            h.add(items)
        self.assertTrue(flagged)  # 21 posts on 10 captions inside a 14-day cooldown must be reported


class QcTest(unittest.TestCase):
    def setUp(self):
        self.h = fresh_hist()
        self.items = plan_day("2026-10-08", ACC, CAP, self.h)

    def rules(self, items, acc=ACC, h=None):
        return {i["rule"] for i in run_qc(items, acc, h or self.h) if i["level"] == "ERROR"}

    def test_same_asset_on_two_accounts(self):
        items = copy.deepcopy(self.items)
        items[1]["asset"] = items[0]["asset"]
        self.assertIn("one_video_one_account", self.rules(items))

    def test_asset_used_before_on_another_account(self):
        old = copy.deepcopy(self.items[0]); old["id"] = "old"; old["date"] = "2026-10-01"
        old["account"] = "someone-else"
        self.h.add([old])
        self.assertIn("one_video_one_account", self.rules(self.items))

    def test_after_cutoff(self):
        items = copy.deepcopy(self.items); items[0]["time"] = "22:15"
        self.assertIn("after_cutoff", self.rules(items))

    def test_min_gap_on_one_account(self):
        items = copy.deepcopy(self.items)
        a = [i for i in items if i["account"] == "acct-a"]
        a[1]["time"] = "10:50"
        self.assertIn("min_gap", self.rules(items))

    def test_burst_across_accounts(self):
        items = copy.deepcopy(self.items)
        for i, t in zip(items[:3], ["10:00", "10:10", "10:20"]):
            i["time"] = t
        self.assertIn("burst", self.rules(items))

    def test_caption_repeat_within_cooldown(self):
        old = copy.deepcopy(self.items[0]); old["id"] = "old"; old["date"] = "2026-10-05"
        self.h.add([old])
        self.assertIn("caption_repeat", self.rules(self.items))

    def test_same_caption_same_hour_on_two_accounts(self):
        items = copy.deepcopy(self.items)
        items[1]["time"] = items[0]["time"]; items[1]["caption"] = items[0]["caption"]
        self.assertIn("caption_same_hour", self.rules(items))

    def test_link_outside_link_slot(self):
        items = copy.deepcopy(self.items)
        first = next(i for i in items if i["link"] is None)
        first["link"] = "example.com/x"
        self.assertIn("link_misplaced", self.rules(items))

    def test_missing_file_when_checking_files(self):
        acc = copy.deepcopy(ACC); acc["settings"]["check_files"] = True
        self.assertIn("missing_file", self.rules(self.items, acc))


class ExportTest(unittest.TestCase):
    def test_ffmpeg_command_contains_the_variation(self):
        cmd = ffmpeg_cmd("in.mp4", "out.mp4", {"speed": 1.2, "zoom": 1.05, "mirror": True})
        for token in ("setpts=PTS/1.2", "hflip", "crop=iw/1.05", "-c:a copy"):
            self.assertIn(token, cmd)

    def test_untouched_variant_has_no_filter(self):
        self.assertNotIn("-vf", ffmpeg_cmd("in.mp4", "out.mp4", {"speed": 1.0, "zoom": 1.0, "mirror": False}))


if __name__ == "__main__":
    unittest.main()
