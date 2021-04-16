import typing

import sqlalchemy as sql
from sqlalchemy import orm

from librarian.storage import (
    base,
    utils,
)


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

    @utils.optional_session
    def custom_promoted_users(self, guild_id, s):
        relations = s.query(DiscordPromotedRelation).filter(DiscordPromotedRelation.guild_id == guild_id).all()
        return {_.user_id for _ in relations}

    @utils.optional_session
    def promote_users(self, guild_id, *user_ids, s=None):
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

    @utils.optional_session
    def demote_users(self, guild_id, *user_ids, s=None):
        existing = s.query(DiscordPromotedRelation).filter(
            DiscordPromotedRelation.guild_id == guild_id,
            DiscordPromotedRelation.user_id.in_(user_ids)
        ).all()
        ids = [_.user_id for _ in existing]

        for obj in existing:
            s.delete(obj)
        return ids

    @utils.optional_session
    def save_messages(self, *messages: typing.List[DiscordMessage], s):
        """ Save multiple messages into the database. """
        s.add_all(messages)

    @utils.optional_session
    def delete_message(self, message_id, channel_id, s):
        s.query(DiscordMessage).filter(
            DiscordMessage.id == message_id,
            DiscordMessage.channel_id == channel_id,
        ).delete()

    @utils.optional_session
    def delete_channel_messages(self, channel_id, s) -> int:
        return s.query(DiscordMessage).filter(
            DiscordMessage.channel_id == channel_id,
        ).delete()

    @utils.optional_session
    def messages_by_pull_numbers(self, *pull_numbers: typing.List[int], s: orm.Session = None):
        """ Return all known messages that are tied to the specified pulls. """
        return s.query(DiscordMessage).filter(DiscordMessage.pull_number.in_(pull_numbers)).all()

    @utils.optional_session
    def all_channels_settings(self, s):
        return s.query(DiscordChannel).all()

    @utils.optional_session
    def load_channel_settings(self, channel_id, s):
        return s.query(DiscordChannel).filter(DiscordChannel.id == channel_id).first()

    @utils.optional_session
    def save_channel_settings(self, channel_id, guild_id, all_settings, s):
        updated = s.query(DiscordChannel).filter(DiscordChannel.id == channel_id).update({"settings": all_settings})
        if not updated:
            s.add(DiscordChannel(id=channel_id, guild_id=guild_id, settings=all_settings))

    @utils.optional_session
    def delete_channel_settings(self, channel_id, s):
        s.query(DiscordChannel).filter(DiscordChannel.id == channel_id).delete()
