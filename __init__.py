import asyncio
import logging
import os
import sys

import yaml

sys.path.append(os.path.dirname(__file__))

from wikiprs import github
from wikiprs import librarian
from wikiprs import routine
from wikiprs import storage


logger = logging.getLogger(__name__)


def setup_logging(filename, loggers):
    formatter = logging.Formatter((
        "%(asctime)s\t"
        "%(module)s:%(lineno)d\t"
        "%(levelname)s\t"
        "%(message)s"
    ))
    file_handler = logging.FileHandler(filename, "a")
    file_handler.setFormatter(formatter)

    for logger in loggers:
        logger.handlers = []
        logger.addHandler(file_handler)
        logger.setLevel(logging.INFO)


def main():
    source_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(source_dir, "config.yaml")
    with open(config_path, "r") as fd:
        config = yaml.safe_load(fd)
    
    setup_logging(
        os.path.join(source_dir, config["logging"]["file"]),
        (logger, github.logger, librarian.logger, routine.logger)
    )

    github_api = github.GitHub(
        token=config["github"]["token"],
        repo=config["github"]["repo"],
    )

    storage_path = os.path.join(source_dir, config["storage"]["path"])
    db = storage.Storage(storage_path)

    client_class = librarian.DummyClient if config["debug"] else librarian.Client
    bot = client_class(
        github=github_api,
        storage=db,
        owner_id=config["discord"]["owner_id"],
        assignee_login=config["github"]["assignee_login"],
        review_channel=config["discord"]["review_channel"],
        review_role_id=config["discord"]["review_role_id"],
    )

    async def start():
        workers = tuple(bot.start_routines())
        main_unit = bot.start(config["discord"]["token"])
        await asyncio.wait(workers + (main_unit,))

    try:
        logger.debug("Bot started")
        bot.loop.run_until_complete(start())
    except KeyboardInterrupt:
        logger.debug("Shutdown started")
        asyncio.new_event_loop().run_until_complete(bot.shutdown())
        logger.debug("Shutdown complete")


if __name__ == "__main__":
    main()
