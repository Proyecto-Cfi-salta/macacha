from agent.admin import repository


def test_crear_admin_y_obtener_por_email(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-1")
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    assert admin["email"] == "admin@macacha.gob.ar"
    assert admin["password_hash"] == "hash-1"
    assert admin["id"]


def test_obtener_admin_por_email_inexistente_devuelve_none(db_conn, clean_db):
    assert repository.obtener_admin_por_email(db_conn, "no-existe@macacha.gob.ar") is None


def test_crear_admin_con_email_repetido_actualiza_el_hash(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-viejo")
    db_conn.commit()
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-nuevo")
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    assert admin["password_hash"] == "hash-nuevo"


def test_obtener_admin_por_id(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-1")
    db_conn.commit()
    creado = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    admin = repository.obtener_admin_por_id(db_conn, creado["id"])

    assert admin == {"id": creado["id"], "email": "admin@macacha.gob.ar"}


def test_obtener_admin_por_id_inexistente_devuelve_none(db_conn, clean_db):
    assert repository.obtener_admin_por_id(db_conn, "00000000-0000-0000-0000-000000000000") is None
