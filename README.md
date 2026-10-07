# social-queue-engine

Plans, quality-checks and exports the **daily posting queue for many social accounts** — so that
nobody has to review 20+ posts one by one before they go out.

Extracted from the system I use to run **14+ accounts as a single operator** (about 22 short-form
videos a day; **9.2 M Reel views and 30,000+ followers in 20 days** across 10 Facebook Pages,
Metricool data, Sep 17 – Oct 6 2026). Pure Python standard library, 18 tests, no accounts or
credentials in this repo — just a framework and a fictional demo config.

```
config/accounts.json ──┐
config/captions.json ──┼─► plan ─► QC ─► export CSV ─► your scheduler
data/history.jsonl  ───┘             ▲        │
        ▲                            │        ▼
        └──────── register ◄── nothing with an ERROR gets exported
```

## What it decides on its own

| Area | Rule |
|---|---|
| **Safe slots** | A proven winner of *that* account, with a small variation (speed 1.0/1.1/1.2 × zoom × mirror). Picks the variant least used in the last 7 days. The best winner takes the link slot. |
| **Test slot** | One slot per account per day carries an experiment (never the link slot), rotating through the day's slots. Pairs with the per-account A/B ladder in [claude-code-agent-team](https://github.com/tomascavernelis/claude-code-agent-team). |
| **Captions** | From a pool; never repeated on the same account inside a cooldown (14 days), never the same text at the same hour on two accounts. |
| **Link** | Only in the account's link slot. |
| **Mirroring** | Only for plain subjects: a logo or a print would read backwards. |

## What QC checks, independently of the planner

`one_video_one_account` (the same clip never lives on two accounts — today *or ever*) ·
`missing_file` · `after_cutoff` · `min_gap` on one account · `burst` across the whole operation
(steady flow, never 3 posts in 30 minutes) · `caption_repeat` · `caption_same_hour` ·
`link_misplaced` / `link_missing`.

The planner and QC are separate on purpose: a planner bug can't hide itself, and hand-edited
queues get the same checks. **Nothing with an ERROR is exported** — `sqe export` refuses.

## Try it

```bash
python3 -m unittest discover -s tests -v        # 18 tests
python3 -m sqe day 2026-10-08                   # plan + QC (exit 1 if any ERROR)
python3 -m sqe export 2026-10-08                # output/2026-10-08-queue.csv for your scheduler
python3 -m sqe register 2026-10-08              # tomorrow's plan now knows what went out
python3 -m sqe day 2026-10-09                   # variants rotate, captions don't repeat
python3 -m sqe read results.csv && python3 -m sqe report   # id,views -> median per account and kind
```

`sqe day` also prints the `ffmpeg` command that renders each variant (it doesn't run them).

## Design notes

- **Per-account data, not global averages.** Winners, tests, slots and links live under each account; nothing is shared except the QC rules.
- **Fail loudly.** If the caption pool is exhausted the planner reuses a caption *and QC reports it* (there's a test for that) instead of silently repeating.
- **Deterministic.** Same config + history + date ⇒ same queue, so a plan can be reviewed, diffed and re-run.
- **History is append-only JSONL** — easy to inspect, merge between machines and feed from analytics.

## Make it yours

Edit `config/accounts.json` (accounts, slots, link slot, winners with their views, tests) and
`config/captions.json`. Set `"check_files": true` to make QC verify that every clip exists.
To add a rule, write one function in `sqe/qc.py` that appends an issue and add a test for it.

## License

MIT
