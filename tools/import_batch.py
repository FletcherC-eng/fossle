#!/usr/bin/env python3
"""Append a batch of new events to events/events.json.

    python3 tools/import_batch.py events/batches/01-curveballs.txt

One event per line, fields separated by " | ":
    title | year | topic | diff | flags | nudge | link clue | short name | fact | pair title
  year      negative for BC
  diff      E (obvious), M (needs more knowledge), N (niche)
  flags     any of: t (curveball), n (internet moment), o (nostalgia), c (circa), g:<group>; "-" for none
            a group stops two events about the same thing landing in one dig
  fact      shown in Field notes (required for a curveball); "-" for none
  pair      curveballs only: the exact title of the event the fact refers to
Blank lines and lines starting with # are ignored. Titles already in the pool are skipped.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "events" / "events.json"


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:48]


def parse(path):
    rows = []
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        f = [x.strip() for x in line.split(" | ")]
        if len(f) not in (9, 10):
            sys.exit(f"{path}:{n}: expected 9 or 10 fields, got {len(f)}: {line[:80]}")
        title, year, topic, diff, flags, h0, h1, h2, fact = f[:9]
        pair = f[9] if len(f) == 10 else ""
        e = {"t": title, "y": int(year), "topic": topic, "diff": diff}
        fl = flags.split() if flags != "-" else []
        for x in fl:
            if x == "c": e["c"] = True
            elif x == "t": e["twist"] = True
            elif x == "n": e["net"] = True
            elif x == "o": e["nos"] = True
            elif x.startswith("g:"): e["group"] = x[2:]
            else: sys.exit(f"{path}:{n}: unknown flag {x}")
        if fact != "-": e["fact"] = fact
        if pair and pair != "-": e["pair"] = pair
        e["h"] = [h0, h1, h2]
        rows.append(e)
    return rows


def main():
    events = json.loads(EVENTS.read_text())
    by_title = {e["t"].lower(): e for e in events}
    ids = {e["id"] for e in events}
    added = []
    for path in sys.argv[1:]:
        for e in parse(path):
            if e["t"].lower() in by_title:
                print(f"skip, already in pool: {e['t']}")
                continue
            base = k = slug(e["t"]); i = 2
            while k in ids:
                k = f"{base}-{i}"; i += 1
            ids.add(k)
            e = {"id": k, **e, "src": Path(path).stem}
            by_title[e["t"].lower()] = e
            events.append(e); added.append(e)
    for e in added:
        if e.get("pair"):
            p = by_title.get(e["pair"].lower())
            if not p:
                sys.exit(f"pair not found for {e['t']}: {e['pair']}")
            e["pair"] = p["id"]
            # the pair must be able to sit in the same dig
            if p["y"] == e["y"]:
                sys.exit(f"{e['t']} and its pair share a year")
    EVENTS.write_text("[\n" + ",\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n]\n")
    print(f"added {len(added)} events, pool now {len(events)}")


if __name__ == "__main__":
    main()
