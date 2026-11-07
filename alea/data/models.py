"""SQLAlchemy models. The schema is owned by Alembic (alea/data/migrations)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

DEFAULT_DB_URL = "sqlite:///alea.db"


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "team"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str | None] = mapped_column(String(120))

    robots: Mapped[list[Robot]] = relationship(back_populates="team")


class Event(Base):
    __tablename__ = "event"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[datetime | None] = mapped_column(DateTime)

    matches: Mapped[list[Match]] = relationship(back_populates="event")


class Match(Base):
    __tablename__ = "match"
    __table_args__ = (UniqueConstraint("event_id", "label"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"))
    label: Mapped[str] = mapped_column(String(40))  # e.g. "Q12"
    red_score: Mapped[int | None] = mapped_column(Integer)
    blue_score: Mapped[int | None] = mapped_column(Integer)

    event: Mapped[Event] = relationship(back_populates="matches")
    log_files: Mapped[list[LogFile]] = relationship(back_populates="match")


class Robot(Base):
    __tablename__ = "robot"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("team.id"))
    name: Mapped[str] = mapped_column(String(120))

    team: Mapped[Team | None] = relationship(back_populates="robots")
    log_files: Mapped[list[LogFile]] = relationship(back_populates="robot")


class LogFile(Base):
    """One imported robot log. Columns after `metadata_json` are the Alea/Meta/* keys."""

    __tablename__ = "log_file"

    id: Mapped[int] = mapped_column(primary_key=True)
    robot_id: Mapped[int | None] = mapped_column(ForeignKey("robot.id"))
    match_id: Mapped[int | None] = mapped_column(ForeignKey("match.id"))
    filename: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    format: Mapped[str] = mapped_column(String(10))  # "rlog" or "wpilog"
    format_version: Mapped[str] = mapped_column(String(10))
    duration_s: Mapped[float] = mapped_column(Float)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    # contract keys that were absent from the log (full Alea/... names)
    missing_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    # how launch detection went (key used, or why it found nothing); see alea/data/launches.py
    launch_note: Mapped[str | None] = mapped_column(String(400))

    contract_version: Mapped[int | None] = mapped_column(Integer)
    red_hive_x_in: Mapped[float | None] = mapped_column(Float)
    blue_hive_x_in: Mapped[float | None] = mapped_column(Float)
    hive_audience_mouth_y_in: Mapped[float | None] = mapped_column(Float)
    hive_rear_mouth_y_in: Mapped[float | None] = mapped_column(Float)
    launch_angle_deg: Mapped[float | None] = mapped_column(Float)
    launcher_exit_behind_in: Mapped[float | None] = mapped_column(Float)
    launcher_max_ticks_per_sec: Mapped[float | None] = mapped_column(Float)

    robot: Mapped[Robot | None] = relationship(back_populates="log_files")
    match: Mapped[Match | None] = relationship(back_populates="log_files")
    shots: Mapped[list[Shot]] = relationship(
        back_populates="log_file", cascade="all, delete-orphan"
    )
    launches: Mapped[list[Launch]] = relationship(
        back_populates="log_file", cascade="all, delete-orphan"
    )


class Shot(Base):
    """One loop's Alea/Aim/* record (the contract has no separate shot-fired key yet)."""

    __tablename__ = "shot"

    id: Mapped[int] = mapped_column(primary_key=True)
    log_file_id: Mapped[int] = mapped_column(ForeignKey("log_file.id"), index=True)
    t_s: Mapped[float] = mapped_column(Float)

    target: Mapped[str | None] = mapped_column(String(20))
    has_pose: Mapped[bool | None] = mapped_column(Boolean)
    distance_in: Mapped[float | None] = mapped_column(Float)
    off_axis_deg: Mapped[float | None] = mapped_column(Float)
    target_heading_deg: Mapped[float | None] = mapped_column(Float)
    heading_error_deg: Mapped[float | None] = mapped_column(Float)
    turn_command: Mapped[float | None] = mapped_column(Float)
    lut_ticks_per_sec: Mapped[float | None] = mapped_column(Float)
    aimed: Mapped[bool | None] = mapped_column(Boolean)
    in_range: Mapped[bool | None] = mapped_column(Boolean)

    log_file: Mapped[LogFile] = relationship(back_populates="shots")


class Launch(Base):
    """One detected ball launch (decision 0007): a sharp flywheel velocity dip.

    The aim columns copy the Alea/Aim/* sample nearest in time, so a launch can be joined to
    what the aim assist believed when the ball left.
    """

    __tablename__ = "launch"

    id: Mapped[int] = mapped_column(primary_key=True)
    log_file_id: Mapped[int] = mapped_column(ForeignKey("log_file.id"), index=True)
    t_s: Mapped[float] = mapped_column(Float)
    flywheel_ticks_per_sec_before: Mapped[float] = mapped_column(Float)
    flywheel_ticks_per_sec_after: Mapped[float] = mapped_column(Float)
    dip_ticks_per_sec: Mapped[float] = mapped_column(Float)

    target: Mapped[str | None] = mapped_column(String(20))
    distance_in: Mapped[float | None] = mapped_column(Float)
    off_axis_deg: Mapped[float | None] = mapped_column(Float)
    heading_error_deg: Mapped[float | None] = mapped_column(Float)
    lut_ticks_per_sec: Mapped[float | None] = mapped_column(Float)
    aimed: Mapped[bool | None] = mapped_column(Boolean)
    in_range: Mapped[bool | None] = mapped_column(Boolean)

    log_file: Mapped[LogFile] = relationship(back_populates="launches")
