#!/usr/bin/env python3
"""Fossle content pipeline.

    python3 tools/fossle.py validate          check events/events.json
    python3 tools/fossle.py schedule --to 90  add days until day 90 exists (or the pool runs dry)
    python3 tools/fossle.py report            runway, what is left, which category runs out first

Rules for every dig (8 cards):
  * 3 easy (E), 2 medium (M), 3 niche (N)
  * exactly one curveball (twist), dealt with the event its fact refers to (pair)
  * exactly one internet moment (net) and one nostalgia pick (nos)
  * no two cards from the same year, at most 2 cards per topic, no two cards from the same group
  * at least two close calls (neighbouring cards within 10 years)
  * an event is used once, ever. Published days are never reshuffled.

Files:
  events/events.json    the pool (edit this)
  events/schedule.json  ledger of which event ids each day used (generated, append only)
  days/NNNN.json        what the game loads for each day (generated)
"""
import argparse, json, random, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "events" / "events.json"
LEDGER = ROOT / "events" / "schedule.json"
DAYS = ROOT / "days"
NEED = {"E": 3, "M": 2, "N": 3}
CARD_FIELDS = ("id", "t", "y", "topic", "diff", "c", "fact", "twist", "net", "nos", "h")


def load_events():
    return json.loads(EVENTS.read_text())


def load_ledger():
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"epoch": "2026-11-06", "days": []}


def validate(events, quiet=False):
    errors, ids, titles = [], set(), set()
    by_id = {e.get("id"): e for e in events}
    for e in events:
        where = e.get("id") or e.get("t") or "?"
        for f in ("id", "t", "y", "topic", "diff", "h"):
            if f not in e:
                errors.append(f"{where}: missing {f}")
        if e.get("id") in ids:
            errors.append(f"{where}: duplicate id")
        ids.add(e.get("id"))
        if e.get("t", "").lower() in titles:
            errors.append(f"{where}: duplicate title")
        titles.add(e.get("t", "").lower())
        if e.get("diff") not in NEED:
            errors.append(f"{where}: diff must be E, M or N")
        if not isinstance(e.get("y"), int) or e["y"] > 2026:
            errors.append(f"{where}: bad year {e.get('y')}")
        h = e.get("h")
        if not (isinstance(h, list) and len(h) == 3 and all(isinstance(x, str) and x.strip() for x in h)):
            errors.append(f"{where}: needs 3 clues [nudge, link to a famous event, short name]")
        elif len(h[2]) > 40:
            errors.append(f"{where}: short name too long")
        if e.get("twist"):
            if not e.get("fact"):
                errors.append(f"{where}: curveball needs a fact")
            if e.get("pair") and e["pair"] not in by_id:
                errors.append(f"{where}: pair {e['pair']} not found")
            if e.get("net") or e.get("nos"):
                errors.append(f"{where}: a curveball can't also be internet or nostalgia")
        if e.get("pair") and not e.get("twist"):
            errors.append(f"{where}: only curveballs have a pair")
        if e.get("net") and e.get("nos"):
            errors.append(f"{where}: pick internet or nostalgia, not both")
        if e.get("t", "").endswith("."):
            errors.append(f"{where}: title ends with a full stop")
    if not quiet:
        print(f"{len(events)} events, {len(errors)} problems")
        for x in errors:
            print("  " + x)
    return errors


def kind(e):
    return "twist" if e.get("twist") else "net" if e.get("net") else "nos" if e.get("nos") else "reg"


def try_build(rnd, avail, by_id):
    ids = {e["id"] for e in avail}
    twists = [e for e in avail if e.get("twist") and (not e.get("pair") or e["pair"] in ids)]
    nets = [e for e in avail if e.get("net")]
    noss = [e for e in avail if e.get("nos")]
    regs = [e for e in avail if kind(e) == "reg"]
    if not twists or not nets or not noss:
        return None
    for _ in range(400):
        tw = rnd.choice(twists)
        chosen = [tw]
        if tw.get("pair"):
            pr = by_id[tw["pair"]]
            if kind(pr) != "reg":
                continue
            chosen.append(pr)
        chosen += [rnd.choice(nets), rnd.choice(noss)]
        if not ok_partial(chosen):
            continue
        pool = regs[:]
        rnd.shuffle(pool)
        for e in pool:
            if len(chosen) == 8:
                break
            if e in chosen:
                continue
            if ok_partial(chosen + [e]):
                chosen.append(e)
        if len(chosen) != 8:
            continue
        ys = sorted((e["y"] for e in chosen), reverse=True)
        close = sum(1 for a, b in zip(ys, ys[1:]) if a - b <= 10)
        if close < 2:
            continue
        return sorted(chosen, key=lambda e: -e["y"])
    return None



def ok_partial(cards):
    need = Counter(e["diff"] for e in cards)
    if any(need[d] > NEED[d] for d in NEED):
        return False
    if len({e["y"] for e in cards}) != len(cards) or len({e["id"] for e in cards}) != len(cards):
        return False
    if any(v > 2 for v in Counter(e["topic"] for e in cards).values()):
        return False
    groups = [e["group"] for e in cards if e.get("group")]
    if len(groups) != len(set(groups)):
        return False
    kinds = Counter(kind(e) for e in cards)
    return kinds["twist"] <= 1 and kinds["net"] <= 1 and kinds["nos"] <= 1


def card(e):
    return {k: e[k] for k in CARD_FIELDS if e.get(k) not in (None, False, "")}


def write_day(day, cards):
    DAYS.mkdir(exist_ok=True)
    rows = ",\n".join(json.dumps(card(e), ensure_ascii=False, separators=(",", ":")) for e in cards)
    (DAYS / f"{day:04d}.json").write_text('{"day":%d,"cards":[\n%s\n]}\n' % (day, rows))


def schedule(to_day):
    events = load_events()
    if validate(events, quiet=True):
        sys.exit("fix validation problems first: python3 tools/fossle.py validate")
    by_id = {e["id"]: e for e in events}
    led = load_ledger()
    used = {i for d in led["days"] for i in d["ids"]}
    missing = [i for i in used if i not in by_id]
    if missing:
        sys.exit(f"ledger uses events that no longer exist: {missing[:5]} (never delete a used event)")
    day = len(led["days"])
    added = 0
    while day < to_day:
        avail = [e for e in events if e["id"] not in used]
        cards = try_build(random.Random(day * 7919 + 101), avail, by_id)
        if not cards:
            print(f"pool ran dry at day {day}")
            break
        led["days"].append({"day": day, "ids": [e["id"] for e in cards]})
        used.update(e["id"] for e in cards)
        write_day(day, cards)
        day += 1
        added += 1
    LEDGER.write_text(json.dumps(led, indent=1) + "\n")
    print(f"added {added} days, schedule now runs to day {len(led['days']) - 1} (Dig {len(led['days']):03d})")
    report(events, led)


def rebuild_days():
    """Rewrite days/*.json from the ledger, e.g. after fixing a typo in an event's text."""
    by_id = {e["id"]: e for e in load_events()}
    led = load_ledger()
    for d in led["days"]:
        write_day(d["day"], sorted((by_id[i] for i in d["ids"]), key=lambda e: -e["y"]))
    print(f"rewrote {len(led['days'])} day files")


def report(events=None, led=None):
    events = events or load_events()
    led = led or load_ledger()
    used = {i for d in led["days"] for i in d["ids"]}
    left = [e for e in events if e["id"] not in used]
    by_id = {e["id"]: e for e in events}
    usable_tw = [e for e in left if e.get("twist") and (not e.get("pair") or e["pair"] not in used)]
    c = Counter()
    for e in left:
        c[kind(e)] += 1
        if kind(e) == "reg":
            c["reg " + e["diff"]] += 1
        c["all " + e["diff"]] += 1
    print(f"scheduled days: {len(led['days'])}   unused events: {len(left)}")
    print(f"  usable curveballs {len(usable_tw)}, internet {c['net']}, nostalgia {c['nos']}")
    print(f"  easy {c['all E']}, medium {c['all M']}, niche {c['all N']}  (need 3/2/3 a day)")
    est = min(len(usable_tw), c["net"], c["nos"], c["all E"] // 3, c["all M"] // 2, c["all N"] // 3)
    print(f"  rough days left in the pool: {est}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    s = sub.add_parser("schedule"); s.add_argument("--to", type=int, required=True)
    sub.add_parser("report")
    sub.add_parser("rebuild")
    a = ap.parse_args()
    if a.cmd == "validate":
        sys.exit(1 if validate(load_events()) else 0)
    if a.cmd == "schedule":
        schedule(a.to)
    if a.cmd == "report":
        report()
    if a.cmd == "rebuild":
        rebuild_days()


if __name__ == "__main__":
    main()
