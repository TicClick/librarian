"""
add assignees

Revision ID: c45dc1355fd1
Revises: fae673b8e597
Create Date: 2021-02-11 16:16:20.774530
"""

from alembic import op
import sqlalchemy as sql


# revision identifiers, used by Alembic.
revision = 'c45dc1355fd1'
down_revision = 'fae673b8e597'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pulls", sql.Column("assignees_logins", sql.JSON, default=[]))


def downgrade():
    with op.batch_alter_table("pulls") as batch_op:
        batch_op.drop_column("assignees_logins")
