"""Match and log viewer."""

import streamlit as st
from sqlalchemy import inspect, select

from alea.data import db
from alea.data.models import Event, Launch, LogFile, Match
from alea.web import common, logs_demo

st.set_page_config(page_title="Match logs", layout="wide")
source = common.data_source_selector()
st.title("Match logs")


def show_synthetic() -> None:
    seed = int(st.sidebar.number_input("Seed", min_value=0, value=0, step=1))
    log = logs_demo.load_demo(seed)
    st.caption("Synthetic match: seeded fake robot log, launches detected by alea.data.launches.")
    st.write(log.note)
    marks = {x.t_s for x in log.launches}
    chart = {
        "t_s": log.t_s,
        "flywheel_ticks_per_sec": log.flywheel_ticks_per_sec,
        "launch_ticks_per_sec": [
            v if t in marks else None
            for t, v in zip(log.t_s, log.flywheel_ticks_per_sec, strict=True)
        ],
    }
    st.line_chart(chart, x="t_s", y=["flywheel_ticks_per_sec", "launch_ticks_per_sec"])
    st.subheader("Detected launches")
    st.dataframe(logs_demo.launch_rows(log), use_container_width=True)


def show_real() -> None:
    url = st.text_input("Database URL", value=db.default_url())
    try:
        engine = db.make_engine(url)
        if not inspect(engine).has_table("log_file"):
            st.info(
                "No ALEA tables in this database yet. "
                "Import logs with `python -m alea.data import`."
            )
            return
        with db.make_session(engine) as session:
            logs = session.execute(
                select(LogFile, Match.label, Event.code)
                .outerjoin(Match, LogFile.match_id == Match.id)
                .outerjoin(Event, Match.event_id == Event.id)
                .order_by(LogFile.id)
            ).all()
            if not logs:
                st.info("The database has no imported logs yet.")
                return
            st.dataframe(
                [
                    {
                        "id": lf.id,
                        "file": lf.filename,
                        "event": code,
                        "match": label,
                        "duration_s": lf.duration_s,
                        "launch_note": lf.launch_note,
                    }
                    for lf, label, code in logs
                ],
                use_container_width=True,
            )
            chosen = st.selectbox("Log", [lf.id for lf, _, _ in logs])
            launches = session.scalars(
                select(Launch).where(Launch.log_file_id == chosen).order_by(Launch.t_s)
            ).all()
            st.subheader("Launches")
            if launches:
                st.dataframe(
                    [
                        {
                            "t_s": x.t_s,
                            "dip_ticks_per_sec": x.dip_ticks_per_sec,
                            "distance_in": x.distance_in,
                            "aimed": x.aimed,
                            "in_range": x.in_range,
                        }
                        for x in launches
                    ],
                    use_container_width=True,
                )
            else:
                st.info("No launches detected in this log.")
    except Exception as exc:  # bad URL, locked file, ...: show it, do not crash the page
        st.warning(f"Could not read the database: {exc}")


if source == "synthetic":
    show_synthetic()
else:
    show_real()
