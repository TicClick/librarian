"""
add channel settings

Revision ID: 5de1a9f1e6fa
Revises: c45dc1355fd1
Create Date: 2021-02-22 17:21:23.934069
"""

from alembic import op
import sqlalchemy as sql
from sqlalchemy.ext import declarative


# revision identifiers, used by Alembic.
revision = '5de1a9f1e6fa'
down_revision = 'c45dc1355fd1'
branch_labels = None
depends_on = None


Base = declarative.declarative_base()


class DiscordPromotedRelation(Base):
    __tablename__ = "promoted_relation"

    id = sql.Column(sql.Integer, primary_key=True)
    guild_id = sql.Column(sql.BigInteger)
    user_id = sql.Column(sql.BigInteger)


class DiscordChannel(Base):
    __tablename__ = "channel"

    id = sql.Column(sql.BigInteger, primary_key=True)
    guild_id = sql.Column(sql.BigInteger)
    settings = sql.Column(sql.JSON, default={})


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade():
    for table_cls in (DiscordChannel, DiscordPromotedRelation):
        op.drop_table(table_cls.__tablename__)
