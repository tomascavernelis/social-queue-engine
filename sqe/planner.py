"""Builds a day's queue from each account's winners and tests.

Rules baked in (each one is checked again, independently, by qc.py):
  * SAFE slot  = a proven winner of THAT account with a small variation (speed / zoom / mirror),
                 the least-used variation of the last N days. The best winner takes the link slot.
  * TEST slot  = one slot per day carries an experiment, rotating through the day's slots.
  * Captions   = from a pool, never repeated on the same account within the cooldown, and never the
                 same caption at the same time on two accounts.
  * Link       = only in the account's link slot.
"""
import itertools

from .history import History
from .util import parse_date

SPEEDS = [1.0, 1.1, 1.2]
ZOOMS = [1.0, 1.05]


def variant_space(winner):
    # Mirroring flips any logo or print, so it is only allowed on plain (logo-free) subjects.
    mirrors = [False, True] if winner.get("plain") else [False]
    return [{"speed": s, "zoom": z, "mirror": m} for s, z, m in itertools.product(SPEEDS, ZOOMS, mirrors)]


def vkey(v):
    return f"{v['speed']}|{v['zoom']}|{int(v['mirror'])}"


def pick_variant(winner, used):
    space = variant_space(winner)
    return min(space, key=lambda v: (used[vkey(v)], space.index(v)))


def pick_caption(pool, avoid, rotation):
    fresh = [c for c in pool if c not in avoid]
    if fresh:
        return fresh[rotation % len(fresh)]
    return pool[rotation % len(pool)]  # pool exhausted: reuse (qc will flag it)


def plan_day(day, accounts_cfg, captions_cfg, hist: History):
    day = parse_date(day)
    s = accounts_cfg["settings"]
    items, caption_at, planned_use, planned_var = [], {}, {}, {}
    ordinal = day.toordinal()

    for acct in accounts_cfg["accounts"]:
        slots = sorted(acct["slots"])
        link_slot = acct.get("link_slot")
        winners = sorted(acct.get("winners", []), key=lambda w: -w.get("views", 0))
        tests = acct.get("tests", [])
        non_link = [t for t in slots if t != link_slot]
        test_slot = non_link[ordinal % len(non_link)] if tests and non_link else None
        pool = captions_cfg.get(acct["network"], [])

        for slot in slots:
            if slot == test_slot:
                t = min(tests, key=lambda x: (hist.test_usage(acct["id"], x["id"]), tests.index(x)))
                asset, kind, variant, file = t, "test", None, t.get("file")
            else:
                if not winners:
                    continue
                if slot == link_slot:
                    w = winners[0]
                else:
                    w = min(winners, key=lambda x: (
                        hist.usage(acct["id"], x["id"], day, s["variant_lookback_days"])
                        + planned_use.get((acct["id"], x["id"]), 0), winners.index(x)))
                planned_use[(acct["id"], w["id"])] = planned_use.get((acct["id"], w["id"]), 0) + 1
                used = hist.variant_counts(acct["id"], w["id"], day, s["variant_lookback_days"])
                for k in planned_var.get((acct["id"], w["id"]), []):
                    used[k] += 1
                variant = pick_variant(w, used)
                planned_var.setdefault((acct["id"], w["id"]), []).append(vkey(variant))
                asset, kind, file = w, "safe", w.get("file")

            avoid = set(hist.captions_on(acct["id"], day, s["caption_cooldown_days"]))
            avoid |= {i["caption"] for i in items if i["account"] == acct["id"]}
            avoid |= caption_at.get(slot, set())  # same hour on another account
            caption = pick_caption(pool, avoid, ordinal + len(items)) if pool else ""
            caption_at.setdefault(slot, set()).add(caption)

            items.append({
                "id": f"{day.isoformat()}-{acct['id']}-{slot.replace(':', '')}",
                "date": day.isoformat(), "time": slot,
                "account": acct["id"], "network": acct["network"],
                "kind": kind, "asset": asset["id"], "file": file,
                "variant": variant, "caption": caption,
                "link": acct.get("link") if slot == link_slot else None,
            })
    return sorted(items, key=lambda i: (i["time"], i["account"]))
