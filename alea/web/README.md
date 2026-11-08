# alea.web

Streamlit app now; FastAPI service later. Entry: `app.py`; pages in `pages/`; synthetic-data
helpers `study_demo.py`, `logs_demo.py` (and `video_demo.py`, `reflection_demo.py`,
`efficiency_demo.py`); `common.py` holds the sidebar data-source selector.

**Roadmap phase:** 6

## Run

```
uv sync --extra web
uv run streamlit run alea/web/app.py
python -m alea.web           # prints the exact command
python -m alea.web --check   # exits non-zero if the web extra is missing
```

## Data source

The sidebar selector stores `synthetic` (default) or `real` in `st.session_state["data_source"]`.
Synthetic shows seeded fake data and needs no files, GPU or network. Real reads your files; with
nothing there a page shows a friendly message instead of failing.

## Pages

1. Shot study (`1_shot_study.py`): results explorer (table, factor effects, worst/best). Real: results directory, default `results/study`.
2. Match logs (`2_match_logs.py`): flywheel velocity with detected launches, launches table. Real: `ALEA_DB_URL` or `sqlite:///alea.db`.
3. Video review (`3_video_review.py`): review match video with tracked events.
4. Match reflection (`4_match_reflection.py`): post-match reflection.
5. Launcher efficiency (`5_launcher_efficiency.py`): launcher efficiency across shots.

## Tests

`tests/test_web_*.py` use `streamlit.testing.v1.AppTest` in synthetic mode, check that real mode
with missing data shows a message, and unit-test the demo helpers. No network.

## Real data needed

- Shot study: a finished study directory (`summary.csv` or `cond_*.npz`) from `just study`.
- Match logs: imported robot logs and match results in the database (`python -m alea.data import`).
  Flywheel velocity curves are drawn only for synthetic logs; the database stores launches and aim samples.
- Video review, match reflection, launcher efficiency: real match footage, reflections and
  launch measurements; see each page.
