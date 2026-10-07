"""sqe day <date>    plan + QC, write output/<date>-queue.json and -qc.json (exit 1 on any ERROR)
sqe plan|qc <date>    the two steps separately
sqe export <date>     CSV for your scheduler — refuses if QC has errors
sqe register <date>   the queue enters the history (so tomorrow's plan knows about it)
sqe read <csv>        load views (columns: id,views) into the history
sqe report            median views per account and kind
"""
import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from .export import ffmpeg_cmd, to_csv
from .history import History
from .planner import plan_day
from .qc import has_errors, run_qc
from .util import load_json

ROOT = Path(__file__).resolve().parent.parent


def paths(args):
    return (ROOT / args.config / "accounts.json", ROOT / args.config / "captions.json",
            ROOT / "data" / "history.jsonl", ROOT / "output")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sqe", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("day", "plan", "qc", "export", "register"):
        sub.add_parser(name).add_argument("date")
    sub.add_parser("read").add_argument("csv")
    sub.add_parser("report")
    args = ap.parse_args(argv)

    acc_p, cap_p, hist_p, out = paths(args)
    accounts, captions, hist = load_json(acc_p), load_json(cap_p), History(hist_p)
    out.mkdir(exist_ok=True)

    if args.cmd in ("day", "plan"):
        items = plan_day(args.date, accounts, captions, hist)
        (out / f"{args.date}-queue.json").write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"planned {len(items)} posts for {len(accounts['accounts'])} accounts -> output/{args.date}-queue.json")
        for it in items:
            if it["variant"]:
                print("  render:", ffmpeg_cmd(it["file"], f"output/{it['id']}.mp4", it["variant"]))

    if args.cmd in ("day", "qc"):
        items = json.loads((out / f"{args.date}-queue.json").read_text(encoding="utf-8"))
        issues = run_qc(items, accounts, hist, base_dir=ROOT)
        (out / f"{args.date}-qc.json").write_text(json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8")
        for i in issues:
            print(f"  {i['level']:5} {i['rule']:20} {i['item']}: {i['message']}")
        print("QC:", "FAILED — nothing with ERROR gets scheduled" if has_errors(issues) else "passed")
        return 1 if has_errors(issues) else 0

    if args.cmd == "export":
        items = json.loads((out / f"{args.date}-queue.json").read_text(encoding="utf-8"))
        if has_errors(run_qc(items, accounts, hist, base_dir=ROOT)):
            print("refusing to export: QC has errors", file=sys.stderr)
            return 1
        to_csv(items, out / f"{args.date}-queue.csv")
        print(f"exported output/{args.date}-queue.csv")

    if args.cmd == "register":
        items = json.loads((out / f"{args.date}-queue.json").read_text(encoding="utf-8"))
        print(f"{hist.add(items)} posts added to the history")

    if args.cmd == "read":
        with open(args.csv, newline="", encoding="utf-8") as f:
            views = {r["id"]: int(r["views"]) for r in csv.DictReader(f)}
        print(f"{hist.set_views(views)} readings merged")

    if args.cmd == "report":
        groups = defaultdict(list)
        for r in hist.rows:
            if "views" in r:
                groups[(r["account"], r["kind"])].append(r["views"])
        for (acct, kind), v in sorted(groups.items()):
            print(f"{acct:12} {kind:5} n={len(v):3} median={statistics.median(v):>9,.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
