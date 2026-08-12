import uuid

from agent import sessions
from agent.admin import contacto_repository
from ingest import repository as repo


def _crear_sesion(conn, session_id):
    sessions.crear_sesion_si_no_existe(conn, session_id)


def _crear_admin(conn, email, rol="admin_organismo", organismo_id=None, activo=True):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO admins (email, password_hash, rol, organismo_id, activo) VALUES (%s, 'hash', %s, %s, %s)",
            (email, rol, organismo_id, activo),
        )


def test_crear_solicitud_devuelve_id(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id)

    solicitud_id = contacto_repository.crear_solicitud(
        db_conn, session_id, None, None, "Juan Pérez", "juan@x.com", "3871234567", "Necesito ayuda"
    )
    db_conn.commit()

    assert solicitud_id
    solicitud = contacto_repository.obtener_solicitud(db_conn, solicitud_id)
    assert solicitud["nombre"] == "Juan Pérez"
    assert solicitud["estado"] == "pendiente"
    assert solicitud["tramite_id"] is None
    assert solicitud["organismo"] is None


def test_crear_solicitud_con_tramite_y_organismo(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id)
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")

    solicitud_id = contacto_repository.crear_solicitud(
        db_conn, session_id, "RC-0001", organismo_id, "Ana", "ana@x.com", "3870000000", "Consulta"
    )
    db_conn.commit()

    solicitud = contacto_repository.obtener_solicitud(db_conn, solicitud_id)
    assert solicitud["tramite_id"] == "RC-0001"
    assert solicitud["tramite_nombre"] == "Actas Regulares"
    assert solicitud["organismo"] == "Registro Civil"


def test_obtener_solicitud_inexistente_devuelve_none(db_conn, clean_db):
    assert contacto_repository.obtener_solicitud(db_conn, str(uuid.uuid4())) is None


def test_actualizar_estado(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id)
    solicitud_id = contacto_repository.crear_solicitud(
        db_conn, session_id, None, None, "Juan", "juan@x.com", "387", "Consulta"
    )
    db_conn.commit()

    contacto_repository.actualizar_estado(db_conn, solicitud_id, "resuelto")
    db_conn.commit()

    assert contacto_repository.obtener_solicitud(db_conn, solicitud_id)["estado"] == "resuelto"


def test_listar_solicitudes_filtra_por_organismo(db_conn, clean_db):
    session_id_a = str(uuid.uuid4())
    session_id_b = str(uuid.uuid4())
    _crear_sesion(db_conn, session_id_a)
    _crear_sesion(db_conn, session_id_b)
    organismo_a = repo.upsert_organismo(db_conn, "Registro Civil")
    organismo_b = repo.upsert_organismo(db_conn, "Rentas")

    contacto_repository.crear_solicitud(
        db_conn, session_id_a, None, organismo_a, "A", "a@x.com", "1", "consulta a"
    )
    contacto_repository.crear_solicitud(
        db_conn, session_id_b, None, organismo_b, "B", "b@x.com", "2", "consulta b"
    )
    db_conn.commit()

    filtradas = contacto_repository.listar_solicitudes(db_conn, organismo_a)
    assert [s["nombre"] for s in filtradas] == ["A"]

    todas = contacto_repository.listar_solicitudes(db_conn, None)
    assert {s["nombre"] for s in todas} == {"A", "B"}


def test_resolver_destinatarios_organismo_con_admin_activo(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    _crear_admin(db_conn, "org@x.com", rol="admin_organismo", organismo_id=organismo_id)
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, organismo_id) == ["org@x.com"]


def test_resolver_destinatarios_organismo_sin_admin_devuelve_super_admins(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    _crear_admin(db_conn, "super@x.com", rol="super_admin", organismo_id=None)
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, organismo_id) == ["super@x.com"]


def test_resolver_destinatarios_sin_organismo_devuelve_super_admins(db_conn, clean_db):
    _crear_admin(db_conn, "super@x.com", rol="super_admin", organismo_id=None)
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, None) == ["super@x.com"]


def test_resolver_destinatarios_ignora_admins_inactivos(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    _crear_admin(db_conn, "org@x.com", rol="admin_organismo", organismo_id=organismo_id, activo=False)
    _crear_admin(db_conn, "super@x.com", rol="super_admin", organismo_id=None, activo=True)
    db_conn.commit()

    assert contacto_repository.resolver_destinatarios(db_conn, organismo_id) == ["super@x.com"]
