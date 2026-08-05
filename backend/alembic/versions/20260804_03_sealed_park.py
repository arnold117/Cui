"""sealed PARK Library boundary

Revision ID: 20260804_03
Revises: 20260804_02
"""
from alembic import op
import sqlalchemy as sa
revision="sealed_park_v1"; down_revision="native_v1"; branch_labels=None; depends_on=None
def upgrade():
 op.create_table("sealed_park_captures",sa.Column("id",sa.Text(),primary_key=True),sa.Column("library_id",sa.Text(),nullable=False),sa.Column("original_text",sa.Text(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
 op.create_table("sealed_park_commands",sa.Column("library_id",sa.Text(),nullable=False),sa.Column("command_id",sa.Text(),nullable=False),sa.Column("command_fingerprint",sa.Text(),nullable=False),sa.Column("capture_id",sa.Text(),nullable=False),sa.Column("result_payload",sa.JSON(),nullable=False),sa.Column("committed_at",sa.DateTime(timezone=True),nullable=False),sa.PrimaryKeyConstraint("library_id","command_id",name="pk_sealed_park_command"),sa.ForeignKeyConstraint(["capture_id"],["sealed_park_captures.id"],name="fk_sealed_park_command_capture"))
def downgrade():
 op.drop_table("sealed_park_commands"); op.drop_table("sealed_park_captures")
