"""Append-only history of what was queued and (optionally) how it performed."""
import json
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

from .util import parse_date


class History:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.rows.append(json.loads(line))

    # --- writes -------------------------------------------------------------
    def add(self, items):
        known = {r["id"] for r in self.rows}
        fresh = [i for i in items if i["id"] not in known]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for i in fresh:
                f.write(json.dumps(i, ensure_ascii=False) + "\n")
        self.rows.extend(fresh)
        return len(fresh)

    def set_views(self, views):
        """views: {item_id: int}. Rewrites the file with the readings merged in."""
        n = 0
        for r in self.rows:
            if r["id"] in views:
                r["views"] = views[r["id"]]
                n += 1
        self.path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in self.rows), encoding="utf-8")
        return n

    # --- reads --------------------------------------------------------------
    def _since(self, today, days):
        cutoff = parse_date(today) - timedelta(days=days)
        return [r for r in self.rows if parse_date(r["date"]) >= cutoff and parse_date(r["date"]) < parse_date(today)]

    def captions_on(self, account, today, days):
        return {r["caption"] for r in self._since(today, days) if r["account"] == account}

    def asset_accounts(self):
        """asset id -> set of accounts it has ever been posted on (one video, one account)."""
        out = defaultdict(set)
        for r in self.rows:
            out[r["asset"]].add(r["account"])
        return out

    def usage(self, account, asset, today, days):
        return sum(1 for r in self._since(today, days) if r["account"] == account and r["asset"] == asset)

    def variant_counts(self, account, asset, today, days):
        c = Counter()
        for r in self._since(today, days):
            if r["account"] == account and r["asset"] == asset and r.get("variant"):
                v = r["variant"]
                c[f"{v['speed']}|{v['zoom']}|{int(v['mirror'])}"] += 1
        return c

    def test_usage(self, account, asset):
        return sum(1 for r in self.rows if r["account"] == account and r["asset"] == asset)
