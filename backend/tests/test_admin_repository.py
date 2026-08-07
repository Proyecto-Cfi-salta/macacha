from agent.admin import repository


def test_crear_admin_y_obtener_por_email(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-1")
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    assert admin["email"] == "admin@macacha.gob.ar"
    assert admin["password_hash"] == "hash-1"
    assert admin["id"]
    assert admin["rol"] == "admin_organismo"
    assert admin["organismo_id"] is None
    assert admin["activo"] is True


def test_crear_admin_con_rol_y_organismo(db_conn, clean_db):
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES ('Registro Civil') RETURNING id")
        organismo_id = cur.fetchone()[0]
    db_conn.commit()

    repository.crear_admin(
        db_conn, "admin@macacha.gob.ar", "hash-1", rol="super_admin", organismo_id=None
    )
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")
    assert admin["rol"] == "super_admin"
    assert admin["organismo_id"] is None


def test_obtener_admin_por_email_inexistente_devuelve_none(db_conn, clean_db):
    assert repository.obtener_admin_por_email(db_conn, "no-existe@macacha.gob.ar") is None


def test_crear_admin_con_email_repetido_actualiza_los_datos(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-viejo")
    db_conn.commit()
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-nuevo", rol="super_admin")
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    assert admin["password_hash"] == "hash-nuevo"
    assert admin["rol"] == "super_admin"


def test_obtener_admin_por_id(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-1")
    db_conn.commit()
    creado = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")

    admin = repository.obtener_admin_por_id(db_conn, creado["id"])

    assert admin == {
        "id": creado["id"],
        "email": "admin@macacha.gob.ar",
        "rol": "admin_organismo",
        "organismo_id": None,
        "activo": True,
    }


def test_obtener_admin_por_id_inexistente_devuelve_none(db_conn, clean_db):
    assert repository.obtener_admin_por_id(db_conn, "00000000-0000-0000-0000-000000000000") is None


def test_listar_admins_incluye_nombre_de_organismo(db_conn, clean_db):
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO organismos (nombre) VALUES ('Registro Civil') RETURNING id")
        organismo_id = cur.fetchone()[0]
    repository.crear_admin(db_conn, "super@macacha.gob.ar", "hash-1", rol="super_admin")
    repository.crear_admin(
        db_conn, "org@macacha.gob.ar", "hash-2", rol="admin_organismo", organismo_id=organismo_id
    )
    db_conn.commit()

    admins = repository.listar_admins(db_conn)

    por_email = {a["email"]: a for a in admins}
    assert por_email["super@macacha.gob.ar"]["organismo"] is None
    assert por_email["org@macacha.gob.ar"]["organismo"] == "Registro Civil"


def test_editar_admin_actualiza_rol_organismo_y_activo(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-1")
    db_conn.commit()
    admin_id = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")["id"]

    repository.editar_admin(db_conn, admin_id, rol="super_admin", organismo_id=None, activo=False)
    db_conn.commit()

    admin = repository.obtener_admin_por_id(db_conn, admin_id)
    assert admin["rol"] == "super_admin"
    assert admin["activo"] is False


def test_editar_admin_con_password_hash_lo_actualiza(db_conn, clean_db):
    repository.crear_admin(db_conn, "admin@macacha.gob.ar", "hash-viejo")
    db_conn.commit()
    admin_id = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")["id"]

    repository.editar_admin(
        db_conn, admin_id, rol="admin_organismo", organismo_id=None, activo=True,
        password_hash="hash-nuevo",
    )
    db_conn.commit()

    admin = repository.obtener_admin_por_email(db_conn, "admin@macacha.gob.ar")
    assert admin["password_hash"] == "hash-nuevo"
