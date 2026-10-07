import csv
import shlex


def ffmpeg_cmd(src, dst, variant):
    """The ffmpeg command that renders a variant (not executed here). Audio is left untouched."""
    vf = []
    if variant["speed"] != 1.0:
        vf.append(f"setpts=PTS/{variant['speed']}")
    if variant["zoom"] != 1.0:
        z = variant["zoom"]
        vf.append(f"scale=iw*{z}:ih*{z},crop=iw/{z}:ih/{z}")
    if variant["mirror"]:
        vf.append("hflip")
    cmd = ["ffmpeg", "-y", "-i", src]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-c:a", "copy", dst]
    return " ".join(shlex.quote(c) for c in cmd)


def to_csv(items, path):
    cols = ["id", "date", "time", "account", "network", "kind", "asset", "file", "caption", "link"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(items)
