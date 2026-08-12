import uuid

from ingest import repository as repo
from agent import sessions
from agent.orchestrator import procesar_turno
from agent.tools import buscar_tramite


def _fake_embed_fn(texts):
    return [[0.0] * 1536 for _ in texts]


def _fake_rerank_fn(query, candidatos):
    return list(range(len(candidatos)))


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


def _armar_tramite_de_prueba(conn, tramite_id="RC-0001", nombre_oficial="Actas Regulares"):
    organismo_id = repo.upsert_organismo(conn, "Registro Civil")
    repo.upsert_tramite(conn, tramite_id, organismo_id, "Actas", nombre_oficial)
    snapshot = {
        "id": tramite_id,
        "nombre_oficial": nombre_oficial,
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
    chunks = [{"tipo_chunk": "descripcion", "texto": nombre_oficial, "fuente_url": "https://x"}]
    embeddings = [[0.0] * 1536]
    repo.insert_version_with_chunks(conn, tramite_id, 1, f"hash-{tramite_id}", snapshot, chunks, embeddings)
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
    assert eventos[-1] == {
        "tipo": "fin",
        "fuentes": [],
        "candidatos_ambiguos": [],
        "sugerir_contacto": False,
    }


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
        "candidatos_ambiguos": [],
        "sugerir_contacto": False,
    }


def test_procesar_turno_con_dos_tramites_preserva_orden_de_citacion(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0002", nombre_oficial="Acta de Matrimonio")
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0001", nombre_oficial="Acta de Nacimiento")
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
                        "function": {
                            "name": "obtener_requisitos",
                            "arguments": '{"tramite_id": "RC-0002"}',
                        },
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "obtener_requisitos",
                            "arguments": '{"tramite_id": "RC-0001"}',
                        },
                    },
                ],
            },
            {
                "role": "assistant",
                "content": "Te cuento las diferencias entre ambas actas.",
                "tool_calls": None,
            },
        ]
    )

    eventos = list(
        procesar_turno(
            db_conn,
            chat_client,
            _fake_embed_fn,
            _fake_rerank_fn,
            session_id,
            "diferencia entre acta de nacimiento y acta de matrimonio",
        )
    )
    db_conn.commit()

    fuentes = eventos[-1]["fuentes"]
    ids_en_orden = [f["tramite_id"] for f in fuentes]
    assert ids_en_orden == ["RC-0002", "RC-0001"]


def test_procesar_turno_busqueda_con_match_unico_cita_la_fuente(db_conn, clean_db):
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
                "content": "Es el trámite de Actas Regulares, mirá el panel para más detalle.",
                "tool_calls": None,
            },
        ]
    )

    eventos = list(
        procesar_turno(
            db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "qué necesito para un acta"
        )
    )
    db_conn.commit()

    assert eventos[-1] == {
        "tipo": "fin",
        "fuentes": [
            {
                "tramite_id": "RC-0001",
                "nombre_oficial": "Actas Regulares",
                "fuente_url": "https://registrocivilsalta.gob.ar/",
            }
        ],
        "candidatos_ambiguos": [],
        "sugerir_contacto": False,
    }


def test_procesar_turno_busqueda_con_varios_candidatos_cita_el_mencionado_en_el_texto(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0002", nombre_oficial="Acta de Matrimonio")
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0001", nombre_oficial="Acta de Nacimiento")
    session_id = str(uuid.uuid4())

    candidatos = buscar_tramite(db_conn, _fake_embed_fn, _fake_rerank_fn, "acta")
    assert len(candidatos) == 2

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
                "content": "El trámite que necesitás es Acta de Nacimiento.",
                "tool_calls": None,
            },
        ]
    )

    eventos = list(
        procesar_turno(
            db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "qué necesito para un acta"
        )
    )
    db_conn.commit()

    fuentes = eventos[-1]["fuentes"]
    assert [f["tramite_id"] for f in fuentes] == ["RC-0001"]


def test_procesar_turno_resuelto_no_expone_candidatos_ambiguos(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0002", nombre_oficial="Acta de Matrimonio")
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0001", nombre_oficial="Acta de Nacimiento")
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
                "content": "El trámite que necesitás es Acta de Nacimiento.",
                "tool_calls": None,
            },
        ]
    )

    eventos = list(
        procesar_turno(
            db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "qué necesito para un acta"
        )
    )
    db_conn.commit()

    assert eventos[-1]["candidatos_ambiguos"] == []


def test_procesar_turno_cita_candidatos_parafraseados_con_nombre_largo(db_conn, clean_db):
    _armar_tramite_de_prueba(
        db_conn,
        tramite_id="TR-0002",
        nombre_oficial="Denuncia laboral (irregularidades, incumplimientos, accidentes, trabajo informal)",
    )
    _armar_tramite_de_prueba(
        db_conn, tramite_id="DC-0001", nombre_oficial="Denuncia/Reclamo ante Defensa del Consumidor"
    )
    session_id = str(uuid.uuid4())

    candidatos = buscar_tramite(db_conn, _fake_embed_fn, _fake_rerank_fn, "denuncia")
    assert len(candidatos) == 2

    respuesta_parafraseada = (
        "Veo que te interesa realizar una denuncia. Por ejemplo, puedes hacer una "
        "Denuncia laboral relacionada con irregularidades, incumplimientos o accidentes, "
        "que gestionan en la Secretaría de Trabajo. También puedes presentar una denuncia "
        "o reclamo ante Defensa del Consumidor."
    )

    chat_client = _FakeChatClient(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "buscar_tramite", "arguments": '{"query": "denuncia"}'},
                    }
                ],
            },
            {"role": "assistant", "content": respuesta_parafraseada, "tool_calls": None},
        ]
    )

    eventos = list(
        procesar_turno(
            db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola como hago una denuncia?"
        )
    )
    db_conn.commit()

    fuentes = eventos[-1]["fuentes"]
    assert {f["tramite_id"] for f in fuentes} == {"TR-0002", "DC-0001"}


def test_procesar_turno_busqueda_ambigua_sin_nombre_en_el_texto_no_cita_fuentes(db_conn, clean_db):
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0002", nombre_oficial="Acta de Matrimonio")
    _armar_tramite_de_prueba(db_conn, tramite_id="RC-0001", nombre_oficial="Acta de Nacimiento")
    session_id = str(uuid.uuid4())

    candidatos = buscar_tramite(db_conn, _fake_embed_fn, _fake_rerank_fn, "acta")
    assert len(candidatos) == 2

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
            {"role": "assistant", "content": "¿Cuál de las dos actas te interesa?", "tool_calls": None},
        ]
    )

    eventos = list(
        procesar_turno(
            db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "qué necesito para un acta"
        )
    )
    db_conn.commit()

    assert eventos[-1]["fuentes"] == []
    candidatos_ambiguos = eventos[-1]["candidatos_ambiguos"]
    assert {c["tramite_id"]: c["descripcion"] for c in candidatos_ambiguos} == {
        "RC-0001": "Descripción",
        "RC-0002": "Descripción",
    }


def test_procesar_turno_busqueda_sin_resultados_no_cita_fuentes(db_conn, clean_db):
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
                        "function": {"name": "buscar_tramite", "arguments": '{"query": "algo inexistente"}'},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "No encontré ningún trámite relacionado.",
                "tool_calls": None,
            },
        ]
    )

    eventos = list(
        procesar_turno(
            db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "algo que no existe"
        )
    )
    db_conn.commit()

    assert eventos[-1] == {
        "tipo": "fin",
        "fuentes": [],
        "candidatos_ambiguos": [],
        "sugerir_contacto": False,
    }


def test_procesar_turno_persiste_los_mensajes_visibles(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    chat_client = _FakeChatClient([{"role": "assistant", "content": "Hola", "tool_calls": None}])

    list(procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola"))
    db_conn.commit()

    visibles = sessions.obtener_mensajes_visibles(db_conn, session_id)
    assert [m["rol"] for m in visibles] == ["user", "assistant"]
    assert [m["contenido"] for m in visibles] == ["hola", "Hola"]


def test_procesar_turno_persiste_el_proveedor_del_chat_client(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    chat_client = _FakeChatClient(
        [{"role": "assistant", "content": "Hola", "tool_calls": None, "proveedor": "gemini"}]
    )

    list(procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola"))
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT proveedor FROM mensajes WHERE session_id = %s AND rol = 'assistant'",
            (session_id,),
        )
        assert cur.fetchone()[0] == "gemini"


def test_procesar_turno_tool_ofrecer_contacto_humano_marca_sugerir_contacto(db_conn, clean_db):
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
                        "function": {"name": "ofrecer_contacto_humano", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": "¿Querés que te ayude una persona? Completá este formulario.",
                "tool_calls": None,
            },
        ]
    )

    eventos = list(
        procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "no entiendo nada")
    )
    db_conn.commit()

    assert eventos[-1]["sugerir_contacto"] is True


def test_procesar_turno_agotar_iteraciones_marca_sugerir_contacto(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    respuesta_con_tool_call_infinita = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_x",
                "type": "function",
                "function": {"name": "buscar_tramite", "arguments": '{"query": "algo"}'},
            }
        ],
    }
    chat_client = _FakeChatClient([respuesta_con_tool_call_infinita] * 6)

    eventos = list(
        procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola")
    )
    db_conn.commit()

    assert eventos[-1]["sugerir_contacto"] is True


def test_procesar_turno_normal_no_marca_sugerir_contacto(db_conn, clean_db):
    session_id = str(uuid.uuid4())
    chat_client = _FakeChatClient(
        [{"role": "assistant", "content": "Hola, en qué te ayudo?", "tool_calls": None}]
    )

    eventos = list(
        procesar_turno(db_conn, chat_client, _fake_embed_fn, _fake_rerank_fn, session_id, "hola")
    )
    db_conn.commit()

    assert eventos[-1]["sugerir_contacto"] is False
