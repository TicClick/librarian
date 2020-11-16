import itertools as it
import os
import sqlite3
import contextlib

import arrow
import sqlalchemy as sql
from sqlalchemy import orm
from sqlalchemy.ext import declarative

PR_STATE_LEN = 32
PR_TITLE_LEN = 512
PR_USER_LOGIN_LEN = 64

Base = declarative.declarative_base()


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

    DIRECT_KEYS = (
        "id", "number", "state", "locked", "title", "created_at", "updated_at", "merged_at",
        "merged", "draft", "review_comments", "commits", "changed_files"
    )
    DATETIME_KEYS = {
        "created_at", "updated_at", "merged_at"
    }
    NESTED_KEYS = (
        "user_login", "user_id"
    )

    def update(self, payload):
        extracted = {}
        for key in self.DIRECT_KEYS:
            if self.id is not None and key == "id":
                continue

            extracted[key] = payload.get(key)
            if key in self.DATETIME_KEYS:
                extracted[key] = arrow.get(extracted[key]).datetime

        for key in self.NESTED_KEYS:
            result = None
            for chunk in key.split("_"):
                result = (payload if result is None else result).get(chunk)
            extracted[key] = result

        super().__init__(**extracted)
    
    def __init__(self, payload):
        self.update(dict(payload))
    
    def url_for(self, repo):
        return f"https://github.com/{repo}/pull/{self.number}"

    @property
    def real_state(self):
        if self.merged:
            return "merged"
        if self.draft:
            return "draft"
        return self.state


class Metadata(Base):
    __tablename__ = "metadata"

    id = sql.Column(sql.Integer, primary_key=True)
    data = sql.Column(sql.PickleType, default=dict())


class DiscordMessage(Base):
    __tablename__ = "embed"

    id = sql.Column(sql.BigInteger, primary_key=True)
    channel_id = sql.Column(sql.BigInteger)
    pull_number = sql.Column(sql.Integer)


class Storage:
    def __init__(self, dbpath):
        self.engine = self.create_engine(f"sqlite:///{dbpath}")
        self.make_session = self.init_session_maker()
        self.create_all_tables()
        
        self.pulls = PullHelper(self)
        self.metadata = MetadataHelper(self)
        self.discord_messages = DiscordMessageHelper(self)

    @staticmethod
    def create_engine(path) -> sql.engine.Engine:
        return sql.create_engine(path, echo=False, convert_unicode=True)

    def init_session_maker(self) -> type(orm.Session):
        return orm.scoped_session(orm.sessionmaker(bind=self.engine, autoflush=False, autocommit=False, expire_on_commit=False))

    def create_all_tables(self):
        Base.metadata.create_all(self.engine)

    @contextlib.contextmanager
    def session_scope(self) -> orm.Session:
        session = self.make_session()
        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()


class Helper:
    def __init__(self, storage):
        self.storage = storage
        self.session_scope = storage.session_scope


class PullHelper(Helper):
    def save_from_payload(self, payload, insert=True):
        self.save(Pull(payload), insert=insert)

    def save(self, pull, insert=True):
        with self.session_scope() as s:
            if insert and s.query(Pull).filter(Pull.number == pull.number).count():
                return
            s.add(pull)

    def save_many_from_payload(self, pulls):
        pulls = {_["number"]: _ for _ in pulls}
        with self.session_scope() as s:
            existing = s.query(Pull).filter(Pull.number.in_(pulls)).all()
            for pull in existing:
                pull.update(pulls[pull.number])
                s.add(pull)

    def by_number(self, pull_number):
        with self.session_scope() as s:
            return s.query(Pull).filter(Pull.number == pull_number).first()

    def remove(self, pull_number):
        with self.session_scope() as s:
            s.query(Pull).filter(Pull.number == pull_number).delete()
        
    def count_merged(self, start_date, end_date):
        with self.session_scope() as s:
            return s.query(Pull).filter(
                Pull.merged == 1,
                Pull.merged_at.between(start_date, end_date)
            ).all()
    
    def active_pulls(self, s):
        return s.query(Pull).filter(Pull.state != "closed").all()


class MetadataHelper(Helper):
    def load(self) -> dict:
        with self.session_scope() as s:
            result = s.query(Metadata).filter().first()
            if result is None:
                result = Metadata(data=dict())
                s.add(result)
            return result.data
    
    def save(self, metadata):
        with self.session_scope() as s:
            result = s.query(Metadata).filter().first()
            result.data = metadata
            s.add(result)

    def load_field(self, key):
        return self.load().get(key)

    def save_field(self, key, value):
        data = self.load()
        data[key] = value
        self.save(data)


class DiscordMessageHelper(Helper):
    def save(self, *messages):
        with self.session_scope() as s:
            for m in messages:
                s.add(m)
    
    def by_pull_numbers(self, *pull_numbers):
        with self.session_scope() as s:
            return s.query(DiscordMessage).filter(DiscordMessage.pull_number.in_(pull_numbers)).all()
