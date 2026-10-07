"""Independent quality control. Nothing with an ERROR gets exported or scheduled."""
from collections import defaultdict
from pathlib import Path

from .history import History
from .util import stamp, to_minutes


def _issue(level, rule, item, msg):
    return {"level": level, "rule": rule, "item": item["id"], "message": msg}


def run_qc(items, accounts_cfg, hist: History, base_dir="."):
    s = accounts_cfg["settings"]
    cfg = {a["id"]: a for a in accounts_cfg["accounts"]}
    out = []

    # one video, one account: never the same asset on two accounts (today or ever before)
    seen = defaultdict(set)
    for it in items:
        seen[it["asset"]].add(it["account"])
    ever = hist.asset_accounts()
    for it in items:
        accts = seen[it["asset"]] | ever.get(it["asset"], set())
        if len(accts) > 1:
            out.append(_issue("ERROR", "one_video_one_account", it,
                              f"asset {it['asset']} would be on {sorted(accts)}"))

    # files exist
    if s.get("check_files"):
        for it in items:
            if not it.get("file") or not (Path(base_dir) / it["file"]).exists():
                out.append(_issue("ERROR", "missing_file", it, f"file not found: {it.get('file')}"))

    # cutoff
    for it in items:
        if to_minutes(it["time"]) > to_minutes(s["no_posts_after"]):
            out.append(_issue("ERROR", "after_cutoff", it, f"{it['time']} is after {s['no_posts_after']}"))

    # spacing inside one account
    by_acct = defaultdict(list)
    for it in items:
        by_acct[it["account"]].append(it)
    for lst in by_acct.values():
        lst.sort(key=stamp)
        for a, b in zip(lst, lst[1:]):
            gap = (stamp(b) - stamp(a)).total_seconds() / 60
            if gap < s["min_gap_minutes"]:
                out.append(_issue("ERROR", "min_gap", b, f"only {gap:.0f} min after {a['time']} on the same account"))

    # bursts across the whole operation (steady flow, not waves)
    ordered = sorted(items, key=stamp)
    n, win = s["max_burst"]["count"], s["max_burst"]["window_minutes"]
    for i in range(len(ordered) - n + 1):
        span = (stamp(ordered[i + n - 1]) - stamp(ordered[i])).total_seconds() / 60
        if span < win:
            out.append(_issue("ERROR", "burst", ordered[i + n - 1],
                              f"{n} posts within {span:.0f} min (limit: fewer than {n} in {win})"))

    # captions: no repeat on an account inside the cooldown, never the same text at the same hour
    for it in items:
        if it["caption"] and it["caption"] in hist.captions_on(it["account"], it["date"], s["caption_cooldown_days"]):
            out.append(_issue("ERROR", "caption_repeat", it, "caption used on this account within the cooldown"))
    same_hour = defaultdict(list)
    for it in items:
        if it["caption"]:
            same_hour[(it["time"], it["caption"])].append(it)
    for lst in same_hour.values():
        if len(lst) > 1:
            for it in lst[1:]:
                out.append(_issue("ERROR", "caption_same_hour", it, "same caption at the same time on another account"))
    for lst in by_acct.values():
        caps = [i["caption"] for i in lst if i["caption"]]
        for it in lst:
            if it["caption"] and caps.count(it["caption"]) > 1:
                out.append(_issue("ERROR", "caption_repeat", it, "caption repeated inside the same day"))

    # link only in the link slot
    for it in items:
        is_link_slot = it["time"] == cfg[it["account"]].get("link_slot")
        if it["link"] and not is_link_slot:
            out.append(_issue("ERROR", "link_misplaced", it, "link outside the link slot"))
        if is_link_slot and not it["link"]:
            out.append(_issue("WARN", "link_missing", it, "link slot without link"))

    return out


def has_errors(issues):
    return any(i["level"] == "ERROR" for i in issues)
