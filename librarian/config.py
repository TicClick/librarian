import os

import yaml


def load(config_path, verbose=False):
    if not config_path:
        raise RuntimeError("Config path is empty")
    if config_path.endswith(".example.yaml"):
        raise RuntimeError("Can't use example config, see the note on its first line")

    if verbose:
        print(f"Loading config from {config_path}")
    with open(config_path, "r") as fd:
        config = yaml.safe_load(fd)

    runtime = config["runtime"]["dir"]
    if not os.path.exists(runtime):   # may happen when Python runtime is in a different directory
        os.makedirs(runtime)
    for path in ("logging.file", "storage.path"):
        root = config
        parts = path.split(".")
        for i, p in enumerate(parts):
            if i < len(parts) - 1:
                root = root[p]
            else:
                root[p] = root[p].format(runtime=runtime)

    return config
