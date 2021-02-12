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


class DiscordPromotedRelation(base.Base):
    __tablename__ = "promoted_relation"

    id = sql.Column(sql.Integer, primary_key=True)
    guild_id = sql.Column(sql.BigInteger)
    user_id = sql.Column(sql.BigInteger)


class DiscordChannel(base.Base):
    __tablename__ = "channel"

    id = sql.Column(sql.BigInteger, primary_key=True)
    guild_id = sql.Column(sql.BigInteger)
    settings = sql.Column(sql.JSON, default={})


class DiscordHelper(base.Helper):
    """
    A class that interfaces a couple of Discord-related tables.
    See individual methods for usage details.
    """

    def custom_promoted_users(self, guild_id):
        with self.session_scope() as s:
            relations = s.query(DiscordPromotedRelation).filter(DiscordPromotedRelation.guild_id == guild_id).all()
            return {_.user_id for _ in relations}

    def promote_users(self, guild_id, *user_ids):
        with self.session_scope() as s:
            existing = s.query(DiscordPromotedRelation).filter(
                DiscordPromotedRelation.guild_id == guild_id,
                DiscordPromotedRelation.user_id.in_(user_ids),
            ).all()
            missing = set(user_ids) - set(_.user_id for _ in existing)

            s.add_all(
                DiscordPromotedRelation(user_id=user_id, guild_id=guild_id)
                for user_id in missing
            )
            return sorted(missing)

    def demote_users(self, guild_id, *user_ids):
        with self.session_scope() as s:
            existing = s.query(DiscordPromotedRelation).filter(
                DiscordPromotedRelation.guild_id == guild_id,
                DiscordPromotedRelation.user_id.in_(user_ids)
            ).all()
            ids = [_.user_id for _ in existing]

            for obj in existing:
                s.delete(obj)
            return ids

    def save_messages(self, *messages: typing.List[DiscordMessage]):
        """ Save multiple messages into the database. """
        with self.session_scope() as s:
            s.add_all(messages)

    def messages_by_pull_numbers(self, *pull_numbers: typing.List[int]):
        """ Return all known messages that are tied to the specified pulls. """
        with self.session_scope() as s:
            return s.query(DiscordMessage).filter(DiscordMessage.pull_number.in_(pull_numbers)).all()
