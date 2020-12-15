def codewrap(obj):
    def inner():
        yield "```"
        if isinstance(obj, (str, bytes)):
            yield obj
        elif hasattr(obj, "__iter__"):
            for elem in obj:
                yield str(elem)
        yield "```"

    return "\n".join(inner())


def pretty_output(cmd, output):
    return codewrap((
        "librarian@librarian:~$ {}".format(" ".join(cmd)),
        output
    ))
