import json

from agent import sessions
from agent.tools import TOOL_SCHEMAS, ejecutar_tool
from ingest.repository import obtener_snapshot_vigente

SYSTEM_PROMPT = (
    "Sos Macacha, la asistente virtual de trámites de la administración pública "
    "de la Provincia de Salta. Hoy tenés información sobre trámites del Registro "
    "Civil. Respondé siempre basándote únicamente en la información que te "
    "devuelven las herramientas disponibles: nunca inventes requisitos, costos, "
    "pasos ni plazos. Si la herramienta buscar_tramite devuelve varios trámites "
    "candidatos y no está claro cuál necesita el usuario, preguntá para "
    "desambiguar antes de usar las demás herramientas. Cuando menciones un "
    "trámite, usá su nombre oficial y, si corresponde, su enlace oficial."
)

MAX_ITERACIONES_TOOLS = 5


def procesar_turno(conn, chat_client, embed_fn, rerank_fn, session_id: str, mensaje_usuario: str):
    sessions.crear_sesion_si_no_existe(conn, session_id)
    historial = sessions.obtener_historial(conn, session_id)

    sessions.guardar_mensaje(conn, session_id, rol="user", contenido=mensaje_usuario)

    messages = (
        [{"role": "system", "content": SYSTEM_PROMPT}]
        + historial
        + [{"role": "user", "content": mensaje_usuario}]
    )

    tramites_citados: set[str] = set()

    for _ in range(MAX_ITERACIONES_TOOLS):
        respuesta = chat_client.completar(messages=messages, tools=TOOL_SCHEMAS)

        if not respuesta["tool_calls"]:
            sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=respuesta["content"])
            yield from _emitir_respuesta_trozeada(respuesta["content"])
            yield {"tipo": "fin", "fuentes": _armar_fuentes(conn, tramites_citados)}
            return

        sessions.guardar_mensaje(
            conn,
            session_id,
            rol="assistant",
            contenido=respuesta["content"],
            tool_calls=respuesta["tool_calls"],
        )
        messages.append(
            {
                "role": "assistant",
                "content": respuesta["content"],
                "tool_calls": respuesta["tool_calls"],
            }
        )

        for tool_call in respuesta["tool_calls"]:
            nombre = tool_call["function"]["name"]
            argumentos = json.loads(tool_call["function"]["arguments"])
            resultado = ejecutar_tool(nombre, argumentos, conn, embed_fn, rerank_fn)

            if nombre == "buscar_tramite":
                tramites_citados.update(candidato["tramite_id"] for candidato in resultado)
            elif "tramite_id" in argumentos:
                tramites_citados.add(argumentos["tramite_id"])

            resultado_json = json.dumps(resultado, ensure_ascii=False)
            sessions.guardar_mensaje(
                conn, session_id, rol="tool", contenido=resultado_json, tool_call_id=tool_call["id"]
            )
            messages.append(
                {"role": "tool", "content": resultado_json, "tool_call_id": tool_call["id"]}
            )

    mensaje_agotado = "No pude resolver tu consulta en este momento. ¿Podés reformularla?"
    sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=mensaje_agotado)
    yield from _emitir_respuesta_trozeada(mensaje_agotado)
    yield {"tipo": "fin", "fuentes": _armar_fuentes(conn, tramites_citados)}


def _emitir_respuesta_trozeada(texto: str):
    for palabra in texto.split(" "):
        yield {"tipo": "texto", "delta": palabra + " "}


def _armar_fuentes(conn, tramites_citados: set[str]) -> list[dict]:
    fuentes = []
    for tramite_id in sorted(tramites_citados):
        snapshot = obtener_snapshot_vigente(conn, tramite_id)
        if snapshot is None:
            continue
        enlaces = snapshot.get("enlaces_oficiales") or []
        fuentes.append(
            {
                "tramite_id": tramite_id,
                "nombre_oficial": snapshot["nombre_oficial"],
                "fuente_url": enlaces[0] if enlaces else None,
            }
        )
    return fuentes
