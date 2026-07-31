from ingest.repository import obtener_snapshot_vigente
from retrieval.hybrid_search import buscar_chunks

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_tramite",
            "description": (
                "Busca trámites relevantes a la pregunta del usuario. Usala "
                "siempre antes de nombrarle a la persona cuál es su trámite, "
                "incluso si te parece obvio cuál es — nunca asumas de "
                "memoria qué trámite corresponde sin confirmarlo primero con "
                "esta herramienta."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "La consulta o pregunta del usuario en lenguaje natural.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_requisitos",
            "description": "Devuelve los requisitos de un trámite ya identificado por su tramite_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_costos_modalidad",
            "description": "Devuelve el costo, la modalidad y la duración estimada de un trámite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_pasos",
            "description": "Devuelve la lista de pasos a seguir para completar un trámite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_normativa",
            "description": "Devuelve el objetivo y la descripción normativa de un trámite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_formularios_enlaces",
            "description": "Devuelve los enlaces oficiales (formularios, sitios de gestión) de un trámite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_problemas_frecuentes",
            "description": "Devuelve los problemas o advertencias frecuentes de un trámite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tramite_id": {"type": "string", "description": "El ID del trámite, ej. 'RC-0001'."}
                },
                "required": ["tramite_id"],
            },
        },
    },
]


def buscar_tramite(conn, embed_fn, rerank_fn, query: str) -> list[dict]:
    chunks = buscar_chunks(query, conn, embed_fn, rerank_fn, top_k=10)
    vistos: set[str] = set()
    resultados: list[dict] = []
    for chunk in chunks:
        if chunk["tramite_id"] not in vistos:
            vistos.add(chunk["tramite_id"])
            resultados.append(
                {
                    "tramite_id": chunk["tramite_id"],
                    "nombre_oficial": chunk["nombre_oficial"],
                    "categoria": chunk["categoria"],
                    "organismo": chunk["organismo"],
                }
            )
    return resultados


def obtener_requisitos(conn, tramite_id: str) -> list[str]:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    return snapshot["requisitos"] if snapshot else []


def obtener_costos_modalidad(conn, tramite_id: str) -> dict:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    if snapshot is None:
        return {}
    return {
        "costo": snapshot["costo"],
        "modalidad": snapshot["modalidad"],
        "duracion": snapshot["duracion"],
    }


def obtener_pasos(conn, tramite_id: str) -> list[str]:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    return snapshot["pasos"] if snapshot else []


def obtener_normativa(conn, tramite_id: str) -> dict:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    if snapshot is None:
        return {}
    return {"objetivo": snapshot["objetivo"], "descripcion": snapshot["descripcion"]}


def obtener_formularios_enlaces(conn, tramite_id: str) -> list[str]:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    return snapshot["enlaces_oficiales"] if snapshot else []


def obtener_problemas_frecuentes(conn, tramite_id: str) -> list[str]:
    snapshot = obtener_snapshot_vigente(conn, tramite_id)
    return snapshot["problemas_frecuentes"] if snapshot else []


def ejecutar_tool(nombre: str, argumentos: dict, conn, embed_fn, rerank_fn):
    if nombre == "buscar_tramite":
        return buscar_tramite(conn, embed_fn, rerank_fn, argumentos["query"])
    if nombre == "obtener_requisitos":
        return obtener_requisitos(conn, argumentos["tramite_id"])
    if nombre == "obtener_costos_modalidad":
        return obtener_costos_modalidad(conn, argumentos["tramite_id"])
    if nombre == "obtener_pasos":
        return obtener_pasos(conn, argumentos["tramite_id"])
    if nombre == "obtener_normativa":
        return obtener_normativa(conn, argumentos["tramite_id"])
    if nombre == "obtener_formularios_enlaces":
        return obtener_formularios_enlaces(conn, argumentos["tramite_id"])
    if nombre == "obtener_problemas_frecuentes":
        return obtener_problemas_frecuentes(conn, argumentos["tramite_id"])
    raise ValueError(f"Tool desconocida: {nombre}")
