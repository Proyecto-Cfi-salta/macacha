import json
import uuid

from fastapi.testclient import TestClient

from agent import api, sessions
from agent.api import obtener_chat_client, obtener_openai_client, obtener_pool


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

    def completar(self, messages, tools):
        respuesta = self._respuestas[self._indice]
        self._indice += 1
        return respuesta


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
