import datetime
import typing

import arrow
import sqlalchemy as sql
from sqlalchemy import orm

from librarian.storage import (
    base,
    utils,
)


PR_STATE_LEN = 32
PR_TITLE_LEN = 512
USER_LOGIN_LEN = 64


class Pull(base.Base):
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
    user_login = sql.Column(sql.String(USER_LOGIN_LEN), nullable=False)
    user_id = sql.Column(sql.Integer, nullable=False)

    # TODO: these fields were designed for a more rich representation and are probably not needed anymore
    added_files = sql.Column(sql.Integer, nullable=False, default=0)
    deleted_files = sql.Column(sql.Integer, nullable=False, default=0)
    changed_files = sql.Column(sql.Integer, nullable=False, default=0)

    assignees_logins = sql.Column(sql.JSON, default=[])

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

        extracted["assignees_logins"] = [_["login"] for _ in payload["assignees"]]
        super().__init__(**extracted)

    def __init__(self, payload: dict):
        self.update(dict(payload))

    def as_dict(self, nested: bool = False, internal: bool = False) -> dict:
        """
        Convert a pull into a dictionary, keeping converted field values as they are.
        `Pull().as_dict()` doesn't equal the initial payload:
        only interesting fields are preserved, and the values such as date stamps are kept converted.

        :param nested: use nested structure for values that were flattened during the object's construction
        :param internal: omit or convert certain fields, such that a model could be initialized from the object
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

        if internal:
            data.pop(self.ID_KEY)
            data["assignees_logins"] = self.assignees_logins
        else:
            data["assignees"] = [{"login": _} for _ in self.assignees_logins]

        return data


class PullHelper(base.Helper):
    """
    A class that interfaces the table with GitHub pulls. See individual methods for usage details.
    """

    @utils.optional_session
    def save_from_payload(self, payload: dict, s: orm.Session, insert: bool = True):
        """
        Save a pull from JSON payload, possibly updating it on existence.

        :param payload: JSON data
        :param s: database session (may be omitted for one-off calls)
        :param insert: don't do anything if the pull already exists
        """

        self.save(Pull(payload), s=s, insert=insert)

    @utils.optional_session
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
            s.query(Pull).filter(Pull.number == pull.number).update(pull.as_dict(internal=True))
        else:
            s.add(pull)

    @utils.optional_session
    def save_many_from_payload(self, pulls_list: typing.List[dict], s: orm.Session) -> typing.List[Pull]:
        """
        Save and update multiple pulls from a list of JSON payloads
        and return ORM objects.

        :param pulls: a list of pulls in form of JSON data.
        :param s: database session (may be omitted for one-off calls)
        """

        pulls = {_["number"]: _ for _ in pulls_list}

        existing = s.query(Pull).filter(Pull.number.in_(pulls)).all()
        for pull in existing:
            pull.update(pulls[pull.number])

        new = [
            Pull(p)
            for num, p in pulls.items() if
            num not in set(_.number for _ in existing)
        ]
        s.add_all(existing)
        s.add_all(new)

        return sorted(existing + new, key=lambda p: p.number)

    @utils.optional_session
    def by_number(self, pull_number: int, s: orm.Session) -> typing.Optional[Pull]:
        """ Return a pull by its number, if it exists. """
        return s.query(Pull).filter(Pull.number == pull_number).first()

    @utils.optional_session
    def remove(self, pull_number: int, s: orm.Session):
        """ Delete a pull by its number. """
        s.query(Pull).filter(Pull.number == pull_number).delete()

    @utils.optional_session
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

    @utils.optional_session
    def active_pulls(self, s: orm.Session):
        """ List all currently open pulls. """
        return s.query(Pull).filter(Pull.state != "closed").all()
