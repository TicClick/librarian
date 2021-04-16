class LibrarianException(Exception):
    pass


class NoDiscordChannel(LibrarianException):
    def __init__(self, channel_id):
        self.channel_id = channel_id
        super().__init__(f"Discord channel #{channel_id} does not exist")
