"""
create all tables

Revision ID: fae673b8e597
Revises:
Create Date: 2021-02-10 21:29:05.128855
"""

from alembic import op
import sqlalchemy as sql
from sqlalchemy import orm
from sqlalchemy.ext import declarative


# revision identifiers, used by Alembic.
revision = 'fae673b8e597'
down_revision = None
branch_labels = None
depends_on = None

PR_STATE_LEN = 32
PR_TITLE_LEN = 512
PR_USER_LOGIN_LEN = 64

Base = declarative.declarative_base()


# Copy the initial tables from librarian.storage as-is to version them

class Pull(Base):
    __tablename__ = "pulls"

    id = sql.Column(sql.Integer, primary_key=True)
    number = sql.Column(sql.Integer, nullable=False)
    state = sql.Column(sql.String(PR_STATE_LEN), nullable=False)
    locked = sql.Column(sql.Integer, nullable=False)
    title = sql.Column(sql.String(PR_TITLE_LEN), nullable=False)
    created_at = sql.Column(sql.DateTime, nullable=False)
    updated_at = sql.Column(sql.DateTime)
    merged_at = sql.Column(sql.DateTime)
    merged = sql.Column(sql.Integer, nullable=False)
    draft = sql.Column(sql.Integer, nullable=False)
    review_comments = sql.Column(sql.Integer, nullable=False)
    commits = sql.Column(sql.Integer, nullable=False)
    user_login = sql.Column(sql.String(PR_USER_LOGIN_LEN), nullable=False)
    user_id = sql.Column(sql.Integer, nullable=False)

    added_files = sql.Column(sql.Integer, nullable=False, default=0)
    deleted_files = sql.Column(sql.Integer, nullable=False, default=0)
    changed_files = sql.Column(sql.Integer, nullable=False, default=0)

    discord_messages = orm.relationship(
        "DiscordMessage", order_by="DiscordMessage.id", back_populates="pull", lazy="joined"
    )


class Metadata(Base):
    __tablename__ = "metadata"

    id = sql.Column(sql.Integer, primary_key=True)
    data = sql.Column(sql.PickleType, default=dict())


class DiscordMessage(Base):
    __tablename__ = "embed"

    id = sql.Column(sql.BigInteger, primary_key=True)
    channel_id = sql.Column(sql.BigInteger)
    pull_number = sql.Column(sql.Integer, sql.ForeignKey("pulls.number"))

    pull = orm.relationship("Pull", back_populates="discord_messages")


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade():
    for table_cls in (Pull, Metadata, DiscordMessage):
        op.drop_table(table_cls.__tablename__)
