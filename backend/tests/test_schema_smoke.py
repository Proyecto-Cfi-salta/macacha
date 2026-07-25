def test_extension_and_tables_exist(db_conn):
    with db_conn.cursor() as cur:
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
        assert {
            "organismos",
            "tramites",
            "tramite_versiones",
            "tramite_chunks",
            "sesiones",
            "mensajes",
            "admins",
        } <= tables
