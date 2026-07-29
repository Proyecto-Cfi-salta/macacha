import json
import urllib.parse
import uuid

from fastapi.testclient import TestClient

from agent import api, sessions
from agent.api import obtener_chat_client, obtener_openai_client, obtener_pool
from ingest import repository as repo


class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        pass


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def connection(self):
        return _FakeConnCtx(self._conn)


class _FakeChatClient:
    def __init__(self, respuestas):
        self._respuestas = respuestas
        self._indice = 0

    def completar_streaming(self, messages, tools):
        respuesta = self._respuestas[self._indice]
        self._indice += 1
        if respuesta.get("content"):
            yield {"tipo": "delta", "texto": respuesta["content"]}
        yield {
            "tipo": "fin",
            "content": respuesta.get("content"),
            "tool_calls": respuesta.get("tool_calls"),
            "proveedor": respuesta.get("proveedor", "openai"),
        }


class _FakeOpenAIClient:
    def generate_embeddings(self, texts):
        return [[0.0] * 1536 for _ in texts]

    def rerank(self, query, candidatos):
        return list(range(len(candidatos)))


def test_post_chat_devuelve_eventos_sse(db_conn, clean_db):
    session_id = str(uuid.uuid4())

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[obtener_chat_client] = lambda: _FakeChatClient(
        [{"role": "assistant", "content": "Hola", "tool_calls": None}]
    )
    api.app.dependency_overrides[obtener_openai_client] = lambda: _FakeOpenAIClient()

    client = TestClient(api.app)
    try:
        respuesta = client.post("/chat", json={"session_id": session_id, "mensaje": "hola"})
        db_conn.commit()
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    lineas = [linea for linea in respuesta.text.split("\n\n") if linea.startswith("data: ")]
    eventos = [json.loads(linea[len("data: ") :]) for linea in lineas]
    assert eventos[-1]["tipo"] == "fin"
    assert "".join(e["delta"] for e in eventos if e["tipo"] == "texto").strip() == "Hola"


def test_post_chat_tool_desconocida_emite_evento_error(db_conn, clean_db):
    session_id = str(uuid.uuid4())

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[obtener_chat_client] = lambda: _FakeChatClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "tool_inexistente", "arguments": "{}"},
                    }
                ],
            }
        ]
    )
    api.app.dependency_overrides[obtener_openai_client] = lambda: _FakeOpenAIClient()

    client = TestClient(api.app)
    try:
        respuesta = client.post("/chat", json={"session_id": session_id, "mensaje": "hola"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    lineas = [linea for linea in respuesta.text.split("\n\n") if linea.startswith("data: ")]
    eventos = [json.loads(linea[len("data: ") :]) for linea in lineas]
    assert eventos[-1]["tipo"] == "error"


def test_post_chat_session_id_invalido_devuelve_422(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[obtener_chat_client] = lambda: _FakeChatClient(
        [{"role": "assistant", "content": "Hola", "tool_calls": None}]
    )
    api.app.dependency_overrides[obtener_openai_client] = lambda: _FakeOpenAIClient()

    client = TestClient(api.app)
    try:
        respuesta = client.post("/chat", json={"session_id": "no-es-un-uuid", "mensaje": "hola"})
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 422


def test_get_mensajes_devuelve_historial_visible(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    sessions.crear_sesion_si_no_existe(db_conn, session_id)
    sessions.guardar_mensaje(db_conn, session_id, rol="user", contenido="hola")
    sessions.guardar_mensaje(db_conn, session_id, rol="assistant", contenido="hola, en qué te ayudo?")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)

    client = TestClient(api.app)
    try:
        respuesta = client.get(f"/sesiones/{session_id}/mensajes")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert [m["rol"] for m in cuerpo] == ["user", "assistant"]


def test_cors_preflight_allows_frontend_origin():
    respuesta = TestClient(api.app).options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_post_chat_incrementa_veces_consultado(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "enlaces_oficiales": ["https://registrocivilsalta.gob.ar/"],
        "telefono_contacto": "",
        "email_contacto": "",
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    db_conn.commit()

    session_id = str(uuid.uuid4())
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    api.app.dependency_overrides[obtener_chat_client] = lambda: _FakeChatClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "obtener_requisitos",
                            "arguments": '{"tramite_id": "RC-0001"}',
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "Necesitás tu DNI.", "tool_calls": None},
        ]
    )
    api.app.dependency_overrides[obtener_openai_client] = lambda: _FakeOpenAIClient()

    client = TestClient(api.app)
    try:
        respuesta = client.post(
            "/chat", json={"session_id": session_id, "mensaje": "qué necesito para un acta"}
        )
        db_conn.commit()
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    with db_conn.cursor() as cur:
        cur.execute("SELECT veces_consultado FROM tramites WHERE id = %s", ("RC-0001",))
        assert cur.fetchone()[0] == 1


def test_get_tramite_devuelve_detalle(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "costo": "Gratuito",
        "modalidad": "Online",
        "duracion": "10 días",
        "pasos": ["Paso 1", "Paso 2"],
        "enlaces_oficiales": ["https://registrocivilsalta.gob.ar/"],
        "telefono_contacto": "0387-4234567",
        "email_contacto": "registrocivil@salta.gob.ar",
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get("/tramites/RC-0001")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "tramite_id": "RC-0001",
        "nombre_oficial": "Actas Regulares",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "requisitos": ["DNI"],
        "costo": "Gratuito",
        "modalidad": "Online",
        "duracion": "10 días",
        "pasos": ["Paso 1", "Paso 2"],
        "enlaces_oficiales": ["https://registrocivilsalta.gob.ar/"],
        "telefono_contacto": "0387-4234567",
        "email_contacto": "registrocivil@salta.gob.ar",
    }


def test_get_tramite_sin_campos_opcionales_devuelve_defaults(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "organismo": "Registro Civil",
        "categoria": "Actas",
        "nombre_oficial": "Actas Regulares",
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "texto", "fuente_url": None}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(db_conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get("/tramites/RC-0001")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["requisitos"] == []
    assert cuerpo["costo"] == ""
    assert cuerpo["modalidad"] == ""
    assert cuerpo["duracion"] == ""
    assert cuerpo["pasos"] == []
    assert cuerpo["enlaces_oficiales"] == []


def test_get_tramite_inexistente_devuelve_404(db_conn, clean_db):
    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get("/tramites/RC-9999")
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 404


def test_get_tramites_frecuentes_devuelve_ranking(db_conn, clean_db):
    organismo_id = repo.upsert_organismo(db_conn, "Registro Civil")
    repo.upsert_tramite(db_conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    repo.upsert_tramite(db_conn, "RC-0002", organismo_id, "Actas", "Actas Especiales")
    db_conn.commit()
    repo.incrementar_veces_consultado(db_conn, "RC-0002")
    repo.incrementar_veces_consultado(db_conn, "RC-0002")
    repo.incrementar_veces_consultado(db_conn, "RC-0001")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get(
            f"/organismos/{urllib.parse.quote('Registro Civil')}/tramites-frecuentes"
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == [
        {"tramite_id": "RC-0002", "nombre_oficial": "Actas Especiales", "veces_consultado": 2},
        {"tramite_id": "RC-0001", "nombre_oficial": "Actas Regulares", "veces_consultado": 1},
    ]


def test_get_tramites_frecuentes_organismo_sin_consultas_devuelve_lista_vacia(db_conn, clean_db):
    repo.upsert_organismo(db_conn, "Registro Civil")
    db_conn.commit()

    api.app.dependency_overrides[obtener_pool] = lambda: _FakePool(db_conn)
    client = TestClient(api.app)
    try:
        respuesta = client.get(
            f"/organismos/{urllib.parse.quote('Registro Civil')}/tramites-frecuentes"
        )
    finally:
        api.app.dependency_overrides.clear()

    assert respuesta.status_code == 200
    assert respuesta.json() == []
