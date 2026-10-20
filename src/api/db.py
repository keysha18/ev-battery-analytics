from collections.abc import Iterator

from fastapi import Request
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .settings import conninfo


def make_pool() -> ConnectionPool:
    return ConnectionPool(conninfo(), min_size=1, max_size=5, kwargs={"row_factory": dict_row}, open=False)


def get_conn(request: Request) -> Iterator[Connection]:
    with request.app.state.pool.connection() as conn:
        yield conn
