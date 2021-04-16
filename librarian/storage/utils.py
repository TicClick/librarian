import inspect

__SESSION_KEYWORD = "s"


def optional_session(f):
    """
    A decorator that lets methods that otherwise require an externally created session
    to be called without it -- the session will be made on the fly. Useful for single calls.
    """

    if __SESSION_KEYWORD not in inspect.signature(f).parameters:
        raise RuntimeError(
            f"for @optional_session to work, {f.__name__} needs to have the `{__SESSION_KEYWORD}` keyword"
        )

    def inner(self, *args, **kwargs):
        if kwargs.get(__SESSION_KEYWORD) is not None:
            return f(self, *args, **kwargs)

        with self.session_scope() as s:
            kwargs[__SESSION_KEYWORD] = s
            return f(self, *args, **kwargs)

    return inner
