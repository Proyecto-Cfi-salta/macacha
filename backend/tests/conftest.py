import os

import psycopg
import pytest
from pgvector.psycopg import register_vector


def _test_database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://macacha:macacha@localhost:5432/macacha_test",
    )


@pytest.fixture
def db_conn():
    conn = psycopg.connect(_test_database_url())
    register_vector(conn)
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def clean_db():
    conn = psycopg.connect(_test_database_url(), autocommit=True)

    def _clean() -> None:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mensajes")
            cur.execute("DELETE FROM sesiones")
            cur.execute("DELETE FROM tramite_chunks")
            cur.execute("DELETE FROM tramite_versiones")
            cur.execute("DELETE FROM admins")
            cur.execute("DELETE FROM tramites")
            cur.execute("DELETE FROM organismos")

    _clean()
    yield
    _clean()
    conn.close()
