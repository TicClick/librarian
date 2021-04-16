"""
remove_file_count_columns

Revision ID: 424c7bd5c88c
Revises: 5de1a9f1e6fa
Create Date: 2021-04-17 00:52:45.990998
"""

from alembic import op
import sqlalchemy as sql


# revision identifiers, used by Alembic.
revision = '424c7bd5c88c'
down_revision = '5de1a9f1e6fa'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite workarounds for ALTER TABLE: https://alembic.sqlalchemy.org/en/latest/batch.html
    with op.batch_alter_table("pulls") as batch_op:
        batch_op.drop_column("added_files")
        batch_op.drop_column("deleted_files")


def downgrade():
    with op.batch_alter_table("pulls") as batch_op:
        batch_op.add_column(sql.Column("added_files", sql.Integer, nullable=False, default=0))
        batch_op.add_column(sql.Column("deleted_files", sql.Integer, nullable=False, default=0))
