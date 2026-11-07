# Fossle content

Every event is used once, ever. Days that are already scheduled never change.

- `events.json` is the pool. Edit text here, never delete an event that has been used.
- `batches/` holds new events in a one line per event format (see `tools/import_batch.py`).
- `schedule.json` records which events each day used. It is generated; don't edit it.
- `../days/NNNN.json` is what the game loads for day NNNN (day 0 is launch day, set by `LAUNCH` in index.html).

## Adding more days

```
python3 tools/import_batch.py events/batches/07-new.txt   # add events
python3 tools/fossle.py validate                           # check them
python3 tools/fossle.py report                             # which category runs out first
python3 tools/fossle.py schedule --to 120                  # extend the schedule
```

Curveballs are usually what runs out first: each one needs a fact and an unused event to pair with.

After fixing a typo in an event that is already scheduled, run `python3 tools/fossle.py rebuild` to rewrite the day files.
