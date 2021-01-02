import contextlib
import datetime
import typing

import arrow
import sqlalchemy as sql
from sqlalchemy import orm
from sqlalchemy.ext import declarative

PR_STATE_LEN = 32
PR_TITLE_LEN = 512
PR_USER_LOGIN_LEN = 64

Base = declarative.declarative_base()


class Pull(Base):
    """
    Internal representation of a GitHub pull request that only stores necessary fields
    (some of them are flattened, see `NESTED_KEYS`).

    Some pulls may have notifications sent out for them via Discord,
    which are recorded in a separate table (see `DiscordMessage`).
    """

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

    # TODO: these fields were designed for a more rich representation and are probably not needed anymore
    added_files = sql.Column(sql.Integer, nullable=False, default=0)
    deleted_files = sql.Column(sql.Integer, nullable=False, default=0)
    changed_files = sql.Column(sql.Integer, nullable=False, default=0)

    discord_messages = orm.relationship(
        "DiscordMessage", order_by="DiscordMessage.id", back_populates="pull", lazy="joined"
    )

    ID_KEY = "id"
    DIRECT_KEYS = (
        ID_KEY, "number", "state", "locked", "title", "created_at", "updated_at", "merged_at",
        "merged", "draft", "review_comments", "commits", "changed_files"
    )
    DATETIME_KEYS = {
        "created_at", "updated_at", "merged_at"
    }
    NESTED_KEYS = (
        "user_login", "user_id"
    )

    def read_nested(self, payload: dict, key: str) -> typing.Any:
        """
        Given an underscore-joined sequence, read the corresponding nested value from a dictionary.
        Example: given `"my_nested_value"`, attempt returning `d["my"]["nested"]["value"]`.
        """

        result = None
        for chunk in key.split("_"):
            result = (payload if result is None else result).get(chunk)
        return result

    def update(self, payload: dict):
        """ Override existing field values by these from the payload. """

        extracted = {}
        for key in self.DIRECT_KEYS:
            if self.id is not None and key == self.ID_KEY:
                continue

            extracted[key] = payload.get(key)
            if key in self.DATETIME_KEYS:
                extracted[key] = arrow.get(extracted[key]).datetime

        for key in self.NESTED_KEYS:
            extracted[key] = self.read_nested(payload, key)

        super().__init__(**extracted)

    def __init__(self, payload: dict):
        self.update(dict(payload))

    def as_dict(self, id: bool = True, nested: bool = False) -> dict:
        """
        Convert a pull into a dictionary, keeping converted field values as they are.
        `Pull().as_dict()` doesn't equal the initial payload:
        only interesting fields are preserved, and the values such as date stamps are kept converted.

        :param id: return a pull with its GitHub identifier (not the same as the pull's number)
        :param nested: use nested structure for values that were flattened during the object's construction
        """

        data = {k: getattr(self, k) for k in self.DIRECT_KEYS + self.NESTED_KEYS}
        if nested:
            for k in self.NESTED_KEYS:
                parts = k.split("_")
                root = data
                v = data.pop(k)
                for i, part in enumerate(parts):
                    if i == len(parts) - 1:
                        root[part] = v
                    else:
                        root = root.setdefault(part, {})

        if not id:
            data.pop(self.ID_KEY)
        return data


class Metadata(Base):
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


class DiscordMessage(Base):
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

        self.pulls = PullHelper(self)
        self.metadata = MetadataHelper(self)
        self.discord_messages = DiscordMessageHelper(self)

    @staticmethod
    def create_engine(path: str) -> sql.engine.Engine:
        return sql.create_engine(path, echo=False)

    def init_session_maker(self) -> orm.Session:
        """ Create a session factory for internal use. """
        return orm.scoped_session(orm.sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False
        ))

    def create_all_tables(self):
        Base.metadata.create_all(self.engine)

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


class Helper:
    """
    Base class for table-specific helpers that includes access to the database and session factory.
    """

    def __init__(self, storage: Storage):
        self.storage = storage
        self.session_scope = storage.session_scope


def optional_session(f):
    """
    A decorator that lets methods that otherwise require an externally created session
    to be called without it -- the session will be made on the fly. Useful for single calls.
    """

    # TODO: explicitly check that a function has an argument called s

    def inner(self, *args, **kwargs):
        session = kwargs.pop("s", None)
        if session is not None:
            return f(self, *args, s=session, **kwargs)

        with self.session_scope() as s:
            return f(self, *args, s=s, **kwargs)

    return inner


class PullHelper(Helper):
    """
    A class that interfaces the table with GitHub pulls. See individual methods for usage details.
    """

    @optional_session
    def save_from_payload(self, payload: dict, s: orm.Session, insert: bool = True):
        """
        Save a pull from JSON payload, possibly updating it on existence.

        :param payload: JSON data
        :param s: database session (may be omitted for one-off calls)
        :param insert: don't do anything if the pull already exists
        """

        self.save(Pull(payload), s=s, insert=insert)

    @optional_session
    def save(self, pull: Pull, s: orm.Session, insert: bool = True):
        """
        Save a pull passed as an ORM object, possibly updating it on existence.

        :param pull: an instance of `Pull`
        :param s: database session (may be omitted for one-off calls)
        :param insert: don't do anything if the pull already exists
        """

        if s.query(Pull).filter(Pull.number == pull.number).count():
            if insert:
                return
            s.query(Pull).filter(Pull.number == pull.number).update(pull.as_dict(id=False))
        else:
            s.add(pull)

    @optional_session
    def save_many_from_payload(self, pulls_list: typing.List[dict], s: orm.Session) -> typing.List[Pull]:
        """
        Save and update multiple pulls from a list of JSON payloads
        and return pulls that existed prior to that.

        :param pulls: a list of pulls in form of JSON data.
        :param s: database session (may be omitted for one-off calls)
        """

        pulls = {_["number"]: _ for _ in pulls_list}

        existing = s.query(Pull).filter(Pull.number.in_(pulls)).all()
        for pull in existing:
            pull.update(pulls[pull.number])

        s.add_all(existing)
        s.add_all([
            Pull(p)
            for num, p in pulls.items() if
            num not in set(_.number for _ in existing)
        ])

        return existing

    @optional_session
    def by_number(self, pull_number: int, s: orm.Session) -> typing.Optional[Pull]:
        """ Return a pull by its number, if it exists. """
        return s.query(Pull).filter(Pull.number == pull_number).first()

    @optional_session
    def remove(self, pull_number: int, s: orm.Session):
        """ Delete a pull by its number. """
        s.query(Pull).filter(Pull.number == pull_number).delete()

    @optional_session
    def count_merged(
        self, start_date: datetime.datetime, end_date: datetime.datetime, s: orm.Session
    ) -> typing.List[Pull]:
        """
        Filter pulls that were merged between two dates. To avoid unintended results,
        pass dates with time, such as start and end of two days, for example,
        `arrow.get().ceil("day").datetime`.

        :param start_date: lower bound (inclusive)
        :param end_date: upper bound (exclusive)
        :param s: database session (may be omitted for one-off calls)
        """

        return s.query(Pull).filter(
            Pull.merged == 1,
            Pull.merged_at.between(start_date, end_date)
        ).all()

    @optional_session
    def active_pulls(self, s: orm.Session):
        """ List all currently open pulls. """
        return s.query(Pull).filter(Pull.state != "closed").all()


class MetadataHelper(Helper):
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


class DiscordMessageHelper(Helper):
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
