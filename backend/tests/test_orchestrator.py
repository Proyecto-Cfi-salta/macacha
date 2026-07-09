import uuid

from ingest import repository as repo
from agent import sessions
from agent.orchestrator import procesar_turno


def _fake_embed_fn(texts):
    return [[0.0] * 1536 for _ in texts]


def _fake_rerank_fn(query, candidatos):
    return list(range(len(candidatos)))


class _FakeChatClient:
    def __init__(self, respuestas):
        self._respuestas = respuestas
        self._indice = 0

    def completar(self, messages, tools):
        respuesta = self._respuestas[self._indice]
        self._indice += 1
        return respuesta


def _armar_tramite_de_prueba(conn):
    organismo_id = repo.upsert_organismo(conn, "Registro Civil")
    repo.upsert_tramite(conn, "RC-0001", organismo_id, "Actas", "Actas Regulares")
    snapshot = {
        "id": "RC-0001",
        "nombre_oficial": "Actas Regulares",
        "requisitos": ["DNI"],
        "costo": "$6000",
        "modalidad": "Online",
        "duracion": "10 días",
        "pasos": ["Paso 1"],
        "objetivo": "Objetivo",
        "descripcion": "Descripción",
        "enlaces_oficiales": ["https://registrocivilsalta.gob.ar/"],
        "problemas_frecuentes": [],
    }
    chunks = [{"tipo_chunk": "descripcion", "texto": "Actas Regulares", "fuente_url": "https://x"}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(conn, "RC-0001", 1, "hash-1", snapshot, chunks, embeddings)
    conn.commit()


def test_procesar_turno_sin_tool_calls(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    chat_client = _FakeChatClient(
        [{"role": "assistant", "content": "Hola, en qué te ayudo?", "tool_calls": None}]
    )

    eventos = list(
        procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola")
    )
    db_conn.commit()

    texto = "".join(e["delta"] for e in eventos if e["tipo"] == "texto")
    assert texto.strip() == "Hola, en qué te ayudo?"
    assert eventos[-1] == {"tipo": "fin", "fuentes": []}


def test_procesar_turno_con_tool_call_arma_fuentes(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    session_id = str(uuid.uuid4())

    chat_client = _FakeChatClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "buscar_tramite", "arguments": '{"query": "acta"}'},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_2",
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

    eventos = list(
        procesar_turno(
            db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "qué necesito para un acta"
        )
    )
    db_conn.commit()

    texto = "".join(e["delta"] for e in eventos if e["tipo"] == "texto")
    assert texto.strip() == "Necesitás tu DNI."
    assert eventos[-1] == {
        "tipo": "fin",
        "fuentes": [
            {
                "tramite_id": "RC-0001",
                "nombre_oficial": "Actas Regulares",
                "fuente_url": "https://registrocivilsalta.gob.ar/",
            }
        ],
    }


def test_procesar_turno_solo_busqueda_no_cita_fuentes(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn)
    session_id = str(uuid.uuid4())

    chat_client = _FakeChatClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "buscar_tramite", "arguments": '{"query": "acta"}'},
                    }
                ],
            },
            {"role": "assistant", "content": "¿Cuál trámite te interesa?", "tool_calls": None},
        ]
    )

    eventos = list(
        procesar_turno(
            db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "qué necesito para un acta"
        )
    )
    db_conn.commit()

    assert eventos[-1] == {"tipo": "fin", "fuentes": []}


def test_procesar_turno_persiste_los_mensajes_visibles(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    chat_client = _FakeChatClient([{"role": "assistant", "content": "Hola", "tool_calls": None}])

    list(procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola"))
    db_conn.commit()

    visibles = sessions.obtener_mensajes_visibles(db_conn, session_id)
    assert [m["rol"] for m in visibles] == ["user", "assistant"]
    assert [m["contenido"] for m in visibles] == ["hola", "Hola"]
