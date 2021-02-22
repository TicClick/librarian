import importlib
import logging
import os


def all_loggers(root_name="librarian"):
    root = importlib.import_module(root_name)
    root_path = os.path.dirname(root.__file__)

    loggers = {}
    for current_root, dirs, files in os.walk(root_path):
        relpath = os.path.relpath(current_root, root_path)
        if relpath == os.path.curdir:
            prefix = root_name
        else:
            prefix = ".".join([root_name] + relpath.split("/"))

        for fn in files:
            if not fn.endswith(".py"):
                continue

            relative_module_name = fn[:-3:]
            module = importlib.import_module(f"{prefix}.{relative_module_name}")
            try:
                loggers[module.__name__] = module.logger
            except AttributeError:
                pass

    return loggers


def setup_logging(runtime_dir, logging_config, loggers):
    formatter = logging.Formatter((
        "%(asctime)s\t"
        "%(module)s:%(lineno)d\t"
        "%(levelname)s\t"
        "%(message)s"
    ))
    file_name = os.path.join(runtime_dir, logging_config["file"])
    file_handler = logging.FileHandler(file_name, "a")
    file_handler.setFormatter(formatter)

    for logger in loggers:
        logger.handlers = []
        logger.addHandler(file_handler)
        logger.setLevel(getattr(logging, logging_config["level"]))
