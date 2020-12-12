import io

# hard limit is 2048. take a bit less to be able to put occasional formatting and stuff
SAFE_EMBED_LENGTH = 2000


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


def iterator(lines):
    buffer = io.StringIO()
    for line in lines:
        if buffer.tell() + len(line) >= SAFE_EMBED_LENGTH:
            yield buffer.getvalue()
            buffer = io.StringIO()

        buffer.write(line)
        buffer.write("\n")

    if buffer.tell():
        yield buffer.getvalue()
