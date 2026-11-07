"""launch table and log_file.launch_note

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("log_file", sa.Column("launch_note", sa.String(length=400), nullable=True))
    op.create_table(
        "launch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("log_file_id", sa.Integer(), nullable=False),
        sa.Column("t_s", sa.Float(), nullable=False),
        sa.Column("flywheel_ticks_per_sec_before", sa.Float(), nullable=False),
        sa.Column("flywheel_ticks_per_sec_after", sa.Float(), nullable=False),
        sa.Column("dip_ticks_per_sec", sa.Float(), nullable=False),
        sa.Column("target", sa.String(length=20), nullable=True),
        sa.Column("distance_in", sa.Float(), nullable=True),
        sa.Column("off_axis_deg", sa.Float(), nullable=True),
        sa.Column("heading_error_deg", sa.Float(), nullable=True),
        sa.Column("lut_ticks_per_sec", sa.Float(), nullable=True),
        sa.Column("aimed", sa.Boolean(), nullable=True),
        sa.Column("in_range", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["log_file_id"], ["log_file.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_launch_log_file_id"), "launch", ["log_file_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_launch_log_file_id"), table_name="launch")
    op.drop_table("launch")
    op.drop_column("log_file", "launch_note")
