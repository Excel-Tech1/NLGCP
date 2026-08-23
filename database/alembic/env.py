"""Alembic migration environment for NLGCP."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import URL, engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _database_url() -> URL:
    """Build the migration URL from environment variables without embedding secrets."""

    required = (
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    )
    missing = [name for name in required if not os.environ.get(name)]

    if missing:
        raise RuntimeError(
            "Database migration environment is missing: " + ", ".join(missing)
        )

    try:
        port = int(os.environ.get("POSTGRES_PORT", "15432"))
    except ValueError as exc:
        raise RuntimeError("POSTGRES_PORT must be an integer") from exc

    return URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        port=port,
        database=os.environ["POSTGRES_DB"],
    )


def run_migrations_offline() -> None:
    """Generate migration SQL without opening a database connection."""

    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured PostgreSQL database."""

    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
