import os

from db.pool import crear_pool
from ingest import repository as repo
from retrieval.vector_search import buscar_por_similitud


def _test_database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql://macacha:macacha@localhost:5432/macacha_test",
    )


def test_pool_connections_support_vector_queries(clean_db):
    pool = crear_pool(_test_database_url())
    try:
        with pool.connection() as conn:
            organismo_id = repo.upsert_organismo(conn, "Registro Civil")
            repo.upsert_tramite(conn, "RC-TEST", organismo_id, "Actas", "Prueba")
            repo.insert_version_with_chunks(
                conn,
                "RC-TEST",
                1,
                "hash-test",
                {"id": "RC-TEST"},
                [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}],
                [[0.0] * 1536],
            )
            conn.commit()

            resultados = buscar_por_similitud(conn, [0.0] * 1536, top_n=5)

        assert len(resultados) == 1
    finally:
        pool.close()
