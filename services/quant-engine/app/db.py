"""PostgreSQL access helpers (sync psycopg, used from threadpool routes and workers).

URL precedence is centralized here: DATABASE_URL_HOST wins (host-run tooling —
migrations, seeds, tests). Containers only set DATABASE_URL (internal network),
so the fallback is correct there.
"""

import os
from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def database_url() -> str:
    url = os.environ.get("DATABASE_URL_HOST") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL (or DATABASE_URL_HOST) must be set for data access.")
    return url


@lru_cache
def get_pool() -> ConnectionPool:
    return ConnectionPool(
        conninfo=database_url(),
        min_size=1,
        max_size=5,
        open=True,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
