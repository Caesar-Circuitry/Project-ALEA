# alea.data

Database models (SQLAlchemy 2 + Alembic) and importers for robot logs. Importers read only the
keys in `docs/robot-interface.md`, listed in `contract.py`.

- `models.py`: Team, Event, Match, Robot, LogFile, Shot, Launch. Default database `sqlite:///alea.db`
  (override with `ALEA_DB_URL`).
- `db.py`, `migrations/`, `/alembic.ini`: engine helpers and Alembic; `db.upgrade(url)` builds the schema.
- `rlog.py`: pure-Python RLOG revision 2 decoder (PsiKit) and a small encoder for test logs.
- `wpilog.py`: `.wpilog` reader, needs the `logs` extra (`uv sync --extra logs`).
- `importer.py`: `import_log(session, path)` for either format. Keys are matched after dropping
  PsiKit's prefixes (`RealOutputs/`, `/RealMetadata/`). One Shot row per loop timestamp; absent
  contract keys stay NULL and are listed in `LogFile.missing_keys`.
- `launches.py`: heuristic launch detector (a flywheel velocity dip under `HardwareMap/*/velocity`);
  `import_log` stores the result as `Launch` rows and `LogFile.launch_note`. See
  [decision 0007](../../docs/decisions/0007-launch-detection.md).
- `matches.py`: `import_matches_csv(session, path)`.
- `synthetic.py`: seeded fake robot logs (150 s, 50 Hz) with known launch times, for tests and notebooks.
- `cli.py`, `__main__.py`: the command line below.

## Command line

```
python -m alea.data import <file|dir> [--db URL] [--robot NAME] [--team N] [--match EVENT:LABEL] [--recursive]
python -m alea.data matches <csv> [--db URL]
python -m alea.data summary [--db URL]
python -m alea.data synth <outdir> [--matches N] [--seed S]
```

`import` upgrades the database first, scans a directory for `.rlog` / `.wpilog`, skips a file whose
sha256 was imported before, prints one status per file (imported, skipped duplicate, failed: reason)
and a count, and exits non-zero if any file failed (a bad file does not stop the others).
`--robot` and `--team` get-or-create a Robot and Team; `--match EVENT:LABEL` get-or-creates the
Event and Match and attaches every imported log to it (import one match's logs per call). The
database is `--db`, else `ALEA_DB_URL`, else `sqlite:///alea.db`.

## Match results CSV

A header row is required. Columns:

| Column | Required | Meaning |
|---|---|---|
| `event_code` | yes | event identifier, e.g. `USCASCMP` |
| `event_name` | no | human name; updates the event if given |
| `label` | yes | match label, e.g. `Q12` |
| `red_score` | yes | integer >= 0, or blank if not played |
| `blue_score` | yes | integer >= 0, or blank if not played |

Rows upsert on (`event_code`, `label`), so re-running a file changes nothing. A bad row stops the
import before anything is written, with its line number. Sample: `tests/data/sample_matches.csv`.
Pulling results from the web (for example FTCScout) is a possible future extension; nothing
fetches over the network today.

**Roadmap phase:** 0
