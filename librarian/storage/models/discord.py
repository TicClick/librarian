import typing

import sqlalchemy as sql
from sqlalchemy import orm

from librarian.storage import base


class DiscordMessage(base.Base):
    """
    Representation of a Discord message, which is used to keep track of sent notifications
    (and possibly other future things). The pull it is tied to can be accessed via the `pull` attribute
    (see `Pull`).
    """

    __tablename__ = "embed"

    id = sql.Column(sql.BigInteger, primary_key=True)
    channel_id = sql.Column(sql.BigInteger)
    pull_number = sql.Column(sql.Integer, sql.ForeignKey("pulls.number"))

    pull = orm.relationship("Pull", back_populates="discord_messages")


class DiscordMessageHelper(base.Helper):
    """
    A class that interfaces the table with Discord messages. See individual methods for usage details.
    """

    def save(self, *messages: typing.List[DiscordMessage]):
        """ Save multiple messages into the database. """
        with self.session_scope() as s:
            s.add_all(messages)

    def by_pull_numbers(self, *pull_numbers: typing.List[int]):
        """ Return all known messages that are tied to the specified pulls. """
        with self.session_scope() as s:
            return s.query(DiscordMessage).filter(DiscordMessage.pull_number.in_(pull_numbers)).all()
