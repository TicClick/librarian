from logging.config import fileConfig
import os
import sys

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

sys.path.append('../librarian')

from librarian import config as librarian_cfg  # noqa


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
alembic_config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(alembic_config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = None

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

CONFIG_PATH_VAR = "LIBRARIAN_CONFIG"


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = context.config.attributes.get("connection", None)
    if connectable is None:
        connectable = engine_from_config(
            alembic_config.get_section(alembic_config.config_ini_section),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


def set_sqlalchemy_url():
    config = librarian_cfg.load(os.getenv(CONFIG_PATH_VAR))
    storage_path = os.path.join(config["runtime"]["dir"], config["storage"]["path"])
    alembic_config.set_main_option("sqlalchemy.url", "sqlite:///{}".format(storage_path))


set_sqlalchemy_url()
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
