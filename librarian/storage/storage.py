import contextlib

import sqlalchemy as sql
from sqlalchemy import orm
from sqlalchemy.ext import declarative

from librarian.storage import base
from librarian.storage.models import (
    discord,
    metadata,
    pull,
)

Base = declarative.declarative_base()


class Storage:
    """
    Facade class for the database, which is responsible for table initialization and maintaining database sessions.
    It also provides access to helper classes, through which one can query individual tables:

        storage = Storage("/tmp/discord.db")
        pull = storage.pulls.by_number(1234)

    Note: database sessions created via the storage itself and helpers don't commit changes automatically.
    """

    def __init__(self, dbpath: str):
        self.engine = self.create_engine(f"sqlite:///{dbpath}")
        self.make_session = self.init_session_maker()
        self.create_all_tables()

        self.pulls = pull.PullHelper(self)
        self.metadata = metadata.MetadataHelper(self)
        self.discord = discord.DiscordHelper(self)

    @staticmethod
    def create_engine(path: str) -> sql.engine.Engine:
        return sql.create_engine(path, echo=False)

    def init_session_maker(self) -> orm.Session:
        """ Create a session factory for internal use. """
        return orm.scoped_session(orm.sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False
        ))

    def create_all_tables(self):
        base.Base.metadata.create_all(self.engine)

    @contextlib.contextmanager
    def session_scope(self) -> orm.Session:
        """
        Context manager that makes sure a new session either commits the changes on leaving the `with` block,
        or rolls them back completely. Usage example:

            with storage.session_scope as session:
                obj = session.query(Pull).count()
                session.add(make_new_pull())

        Note: outside of the test environment, you don't need to use the scope directly.
        Instead, use the one provided by table helpers.
        """

        session = self.make_session()
        try:
            yield session
            session.commit()
        except (Exception, BaseException):
            session.rollback()
            raise
        finally:
            session.close()
