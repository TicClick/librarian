import asyncio
import itertools
import logging
import os

import yaml

from librarian import (
    discord,
    github,
    routine,
    storage,
)


logger = logging.getLogger(__name__)


def setup_logging(source_dir, logging_config, loggers):
    formatter = logging.Formatter((
        "%(asctime)s\t"
        "%(module)s:%(lineno)d\t"
        "%(levelname)s\t"
        "%(message)s"
    ))
    file_name = os.path.join(source_dir, logging_config["file"])
    file_handler = logging.FileHandler(file_name, "a")
    file_handler.setFormatter(formatter)

    for logger in loggers:
        logger.handlers = []
        logger.addHandler(file_handler)
        logger.setLevel(getattr(logging, logging_config["level"]))


def configure_client():
    source_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
    config_path = os.path.join(source_dir, "config/config.yaml")
    with open(config_path, "r") as fd:
        config = yaml.safe_load(fd)

    setup_logging(
        source_dir, config["logging"],
        itertools.chain(
            (logger, github.logger, routine.logger),
            discord.LOGGERS,
        )
    )
    logger.info("%s Starting up %s", "-" * 10, "-" * 10)

    github_api = github.GitHub(
        token=config["github"]["token"],
        repo=config["github"]["repo"],
    )

    storage_path = os.path.join(source_dir, config["storage"]["path"])
    db = storage.Storage(storage_path)

    client = discord.Client(
        github=github_api,
        storage=db,
        owner_id=config["discord"]["owner_id"],
        assignee_login=config["github"]["assignee_login"],
        review_channel=config["discord"]["review_channel"],
        review_role_id=config["discord"]["review_role_id"],
        title_regex=config["github"]["title_regex"],
        store_in_pins=config["discord"]["store_in_pins"],
    )

    client.setup()

    return client, config


def run_client(client, config):
    async def start():
        tasks = list(map(
            asyncio.create_task,
            client.start_routines()
        ))
        tasks.append(asyncio.create_task(
            client.start(config["discord"]["token"])
        ))
        await asyncio.gather(*tasks)

    try:
        logger.debug("Client started")
        client.loop.run_until_complete(start())
    except KeyboardInterrupt:
        logger.debug("Shutdown started")
        asyncio.new_event_loop().run_until_complete(client.shutdown())
        logger.debug("Shutdown complete")


def main():
    run_client(*configure_client())


if __name__ == "__main__":
    main()
