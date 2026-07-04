import os

import psycopg


def test_extension_and_tables_exist():
    conn = psycopg.connect(
        os.environ.get(
            "TEST_DATABASE_URL",
            "postgresql://macacha:macacha@localhost:5432/macacha_test",
        )
    )
    with conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        assert cur.fetchone() is not None

        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
        tables = {row[0] for row in cur.fetchall()}
        assert {"organismos", "tramites", "tramite_versiones", "tramite_chunks"} <= tables
    conn.close()
