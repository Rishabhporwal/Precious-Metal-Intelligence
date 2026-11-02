"""Alembic environment for the PMI database.

Connection URL comes from the DATABASE_URL (or DATABASE_URL_HOST for
host-run tooling) environment variable — never hard-coded here.
"""

import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make app-level modules importable if migrations ever need shared metadata.
QUANT_ENGINE_DIR = Path(__file__).resolve().parents[2] / "services" / "quant-engine"
if str(QUANT_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(QUANT_ENGINE_DIR))

config = context.config


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_URL_HOST")
    if not url:
        raise RuntimeError(
            "DATABASE_URL (or DATABASE_URL_HOST) must be set for Alembic migrations."
        )
    # SQLAlchemy 2.x speaks psycopg3 when the driver segment is +psycopg.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
