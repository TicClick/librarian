import typing

import sqlalchemy as sql

from librarian.storage import base


class Metadata(base.Base):
    """
    Representation of the bot's state in form of dictionary, where meaningful data
    obtained at runtime is stored (for example, the last checked pull number). The data
    must only be composed of any basic Python objects and structures from the standard library:
    pickle doesn't work with lambdas and can't unpickle an object if its housing module has been changed.

    The state should only be accessed via `MetadataHelper`.
    """

    __tablename__ = "metadata"

    id = sql.Column(sql.Integer, primary_key=True)
    data = sql.Column(sql.PickleType, default=dict())


class MetadataHelper(base.Helper):
    """
    A class that interfaces the bot's stored state and lets using it as a key-value storage. Example:

        storage = Storage("/tmp/discord.db")
        storage.metadata.save_field("first_three_numbers", [1, 2, 3])
        secret_numbers = storage.metadata.load_field("first_three_numbers")
    """

    def load(self) -> dict:
        """ Load and return the full state. """
        with self.session_scope() as s:
            result = s.query(Metadata).filter().first()
            if result is None:
                result = Metadata(data=dict())
                s.add(result)
            return result.data

    def save(self, metadata: dict):
        """ Store passed state in the database. """
        with self.session_scope() as s:
            result = s.query(Metadata).filter().first()
            result.data = metadata
            s.add(result)

    def load_field(self, key: str) -> typing.Any:
        """ Access a specific state value by its key. """
        return self.load().get(key)

    def save_field(self, key, value):
        """ Save a single value by its key. """
        data = self.load()
        data[key] = value
        self.save(data)
