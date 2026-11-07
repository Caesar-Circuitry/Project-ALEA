# alea.data

Database models (SQLAlchemy 2 + Alembic) and importers for robot logs. Importers read only the
keys in `docs/robot-interface.md`, listed in `contract.py`.

- `models.py`: Team, Event, Match, Robot, LogFile, Shot. Default database `sqlite:///alea.db`
  (override with `ALEA_DB_URL`).
- `db.py`, `migrations/`, `/alembic.ini`: engine helpers and Alembic; `db.upgrade(url)` builds the schema.
- `rlog.py`: pure-Python RLOG revision 2 decoder (PsiKit) and a small encoder for test logs.
- `wpilog.py`: `.wpilog` reader, needs the `logs` extra (`uv sync --extra logs`).
- `importer.py`: `import_log(session, path)` for either format. Keys are matched after dropping
  PsiKit's prefixes (`RealOutputs/`, `/RealMetadata/`). One Shot row per loop timestamp; absent
  contract keys stay NULL and are listed in `LogFile.missing_keys`.

**Roadmap phase:** 0
