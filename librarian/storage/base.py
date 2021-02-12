from sqlalchemy.ext import declarative

Base = declarative.declarative_base()


class Helper:
    """
    Base class for table-specific helpers that includes access to the database and session factory.
    """

    def __init__(self, storage):
        self.storage = storage
        self.session_scope = storage.session_scope
