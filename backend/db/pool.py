from psycopg_pool import ConnectionPool
from pgvector.psycopg import register_vector


def _configurar_conexion(conn):
    register_vector(conn)


def crear_pool(database_url: str) -> ConnectionPool:
    return ConnectionPool(database_url, configure=_configurar_conexion, open=True)
