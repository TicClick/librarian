import argparse
import logging
import os
import sys

from librarian import (
    config,
    discord,
    logging as logging_utils,
    github,
    storage,
)

logger = logging.getLogger(__name__)

PADDING = 40
PADDING_CHAR = "-"


def configure_client(config):
    # TODO: ban logging.{debug,info,warning,error,critical} which I sometimes call by mistake
    loggers = logging_utils.all_loggers()
    loggers["librarian.main"] = logger  # otherwise an old copy with default settings is kept
    logging_utils.setup_logging(config["runtime"]["dir"], config["logging"], loggers.values())
    logger.info(" Starting up ".center(PADDING, PADDING_CHAR))

    github_api = github.GitHub(
        token=config["github"]["token"],
        repo=config["github"]["repo"],
    )

    storage_path = os.path.join(config["runtime"]["dir"], config["storage"]["path"])
    db = storage.Storage(storage_path)

    client = discord.Client(
        github=github_api,
        storage=db,
        assignee_login=config["github"]["assignee_login"],
    )

    client.setup()
    return client, config


def run_client(client, config):
    try:
        logger.debug("Client started")
        client.loop.run_until_complete(client.start(config["discord"]["token"]))
    except KeyboardInterrupt:
        logger.debug("Shutdown")
        client.loop.run_until_complete(client.close())
        logger.debug(" Shutdown completed ".center(PADDING, PADDING_CHAR))


def parse_args(args=None):
    if args is None:
        args = sys.argv[1:]

    source_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
    default_config_path = os.path.join(source_dir, "config/config.yaml")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", help="Path to the .yaml configuration file", default=default_config_path
    )
    return parser.parse_args(args)


def main():
    args = parse_args()
    cfg = config.load(args.config)
    client, token = configure_client(cfg)
    run_client(client, token)


if __name__ == "__main__":
    main()
