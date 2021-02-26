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
