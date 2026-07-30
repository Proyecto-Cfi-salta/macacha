import json
import re

from agent import sessions
from agent.tools import TOOL_SCHEMAS, ejecutar_tool
from ingest.repository import obtener_snapshot_vigente

SYSTEM_PROMPT = (
    "Sos Macacha, la asistente virtual de trámites de la administración pública "
    "de la Provincia de Salta. Tu objetivo es ayudar a las personas a entender y "
    "completar sus trámites de la forma más simple posible. Sabés que muchos "
    "trámites pueden ser confusos o estresantes, así que tratá a cada persona "
    "con calidez y empatía — como alguien de confianza que se toma el trabajo en "
    "serio, no como un formulario que recita datos. Podés usar un tono cercano y "
    "humano. Contá las cosas como lo haría una persona explicándole a otra: en "
    "oraciones seguidas, no como una lista de trámite. Usá viñetas o numeración "
    "solo si hay varios ítems y de verdad ayuda a leerlos (por ejemplo, más de "
    "cuatro requisitos o pasos) — nunca como formato por defecto. Variá cómo "
    "empezás y cerrás cada respuesta: no repitas la misma pregunta de cierre en "
    "todos los mensajes. Si la persona comenta que algo le resulta tedioso, "
    "confuso o frustrante, reconocelo antes de pasar a la información, en vez "
    "de ignorarlo. No uses emojis. No anuncies que vas a usar una "
    "herramienta antes de usarla (nada de \"voy a buscar esto, un "
    "momento\") — respondé directo con el resultado. Además de vos, la "
    "persona tiene a la vista un panel con los datos duros del trámite "
    "(requisitos, costo, modalidad, duración, pasos y enlaces oficiales) "
    "en cuanto identificás cuál es. Nunca detalles los requisitos ni los "
    "pasos de un trámite en el chat a menos que te los pidan "
    "explícitamente (por ejemplo, \"cuáles son los requisitos\", o un "
    "mensaje pidiendo aclarar esa sección puntual) — si no te los piden "
    "así, decí simplemente que están en el panel de al lado, sin "
    "describirlos ni resumirlos. Un pedido vago como \"contame más\", "
    "\"dame más información\" o \"explicame mejor\" NO cuenta como pedido "
    "explícito de requisitos ni de pasos — ante eso, respondé igual que "
    "al identificar el trámite (breve, señalando el panel), a menos que "
    "la persona nombre específicamente qué sección quiere. Cuando "
    "identifiques un trámite por "
    "primera vez, respondé en una o dos oraciones (qué trámite es y, si "
    "suma, algún dato saliente como si es gratuito o rápido) e invitá a "
    "mirar el panel o a preguntar algo puntual. Si te preguntan un dato "
    "puntual (por ejemplo, solo el costo, o solo la modalidad), respondé "
    "únicamente ese dato — no agrupes campos relacionados que no te "
    "pidieron (si preguntan el costo, no sumes de yapa la modalidad o la "
    "duración). Si te piden explícitamente los requisitos o los pasos, "
    "ahí sí detallalos completos, sin traer datos de otras secciones. Sin "
    "perder precisión: respondé siempre basándote "
    "únicamente en la información que te devuelven las herramientas "
    "disponibles, nunca inventes requisitos, costos, pasos ni plazos. Nunca "
    "le digas a la persona cuál es su trámite ni lo nombres como si ya "
    "estuviera identificado sin haber llamado antes a buscar_tramite en "
    "algún momento de esta conversación para confirmarlo — aunque te "
    "parezca obvio de qué trámite se trata, no lo asumas de memoria, "
    "buscalo primero. Si la "
    "herramienta buscar_tramite devuelve varios trámites candidatos y no está "
    "claro cuál necesita la persona, preguntá con calidez para desambiguar "
    "antes de usar las demás herramientas. Cuando menciones un trámite, usá su "
    "nombre oficial."
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

    tramites_citados: list[str] = []
    candidatos_buscados: dict[str, str] = {}

    for _ in range(MAX_ITERACIONES_TOOLS):
        contenido = ""
        tool_calls = None
        proveedor = None

        for evento in chat_client.completar_streaming(messages=messages, tools=TOOL_SCHEMAS):
            if evento["tipo"] == "delta":
                yield {"tipo": "texto", "delta": evento["texto"]}
            else:
                contenido = evento["content"]
                tool_calls = evento["tool_calls"]
                proveedor = evento["proveedor"]

        if not tool_calls:
            _citar_candidatos_mencionados(contenido, candidatos_buscados, tramites_citados)
            sessions.guardar_mensaje(
                conn,
                session_id,
                rol="assistant",
                contenido=contenido,
                proveedor=proveedor,
            )
            yield {
                "tipo": "fin",
                "fuentes": _armar_fuentes(conn, tramites_citados),
                "candidatos_ambiguos": (
                    [] if tramites_citados else _armar_candidatos_ambiguos(conn, candidatos_buscados)
                ),
            }
            return

        sessions.guardar_mensaje(
            conn,
            session_id,
            rol="assistant",
            contenido=contenido,
            tool_calls=tool_calls,
            proveedor=proveedor,
        )
        messages.append(
            {
                "role": "assistant",
                "content": contenido,
                "tool_calls": tool_calls,
            }
        )

        for tool_call in tool_calls:
            nombre = tool_call["function"]["name"]
            argumentos = json.loads(tool_call["function"]["arguments"])
            resultado = ejecutar_tool(nombre, argumentos, conn, embed_fn, rerank_fn)

            if "tramite_id" in argumentos and argumentos["tramite_id"] not in tramites_citados:
                tramites_citados.append(argumentos["tramite_id"])
            elif nombre == "buscar_tramite":
                if len(resultado) == 1:
                    tramite_id_unico = resultado[0]["tramite_id"]
                    if tramite_id_unico not in tramites_citados:
                        tramites_citados.append(tramite_id_unico)
                else:
                    for candidato in resultado:
                        candidatos_buscados[candidato["tramite_id"]] = candidato["nombre_oficial"]

            resultado_json = json.dumps(resultado, ensure_ascii=False)
            sessions.guardar_mensaje(
                conn, session_id, rol="tool", contenido=resultado_json, tool_call_id=tool_call["id"]
            )
            messages.append(
                {"role": "tool", "content": resultado_json, "tool_call_id": tool_call["id"]}
            )

    mensaje_agotado = "No pude resolver tu consulta en este momento. ¿Podés reformularla?"
    sessions.guardar_mensaje(conn, session_id, rol="assistant", contenido=mensaje_agotado)
    yield {"tipo": "texto", "delta": mensaje_agotado}
    yield {
        "tipo": "fin",
        "fuentes": _armar_fuentes(conn, tramites_citados),
        "candidatos_ambiguos": (
            [] if tramites_citados else _armar_candidatos_ambiguos(conn, candidatos_buscados)
        ),
    }


_STOPWORDS = {"de", "del", "la", "el", "los", "las", "en", "con", "ante", "y", "o", "a", "al", "un", "una"}
_UMBRAL_COINCIDENCIA = 0.7


def _normalizar(texto: str) -> str:
    sin_parentesis = re.sub(r"\([^)]*\)", " ", texto)
    solo_palabras = re.sub(r"[^\w\s]", " ", sin_parentesis, flags=re.UNICODE)
    return re.sub(r"\s+", " ", solo_palabras).strip().lower()


def _palabras_significativas(nombre_normalizado: str) -> list[str]:
    return [p for p in nombre_normalizado.split() if len(p) >= 4 and p not in _STOPWORDS]


def _citar_candidatos_mencionados(
    texto: str | None, candidatos: dict[str, str], tramites_citados: list[str]
) -> None:
    if not texto:
        return
    texto_normalizado = _normalizar(texto)
    menciones = []
    for tramite_id, nombre_oficial in candidatos.items():
        palabras = _palabras_significativas(_normalizar(nombre_oficial))
        if not palabras:
            continue
        indices_encontrados = [
            texto_normalizado.find(palabra)
            for palabra in palabras
            if texto_normalizado.find(palabra) != -1
        ]
        if len(indices_encontrados) / len(palabras) >= _UMBRAL_COINCIDENCIA:
            menciones.append((min(indices_encontrados), tramite_id))
    menciones.sort()
    for _, tramite_id in menciones:
        if tramite_id not in tramites_citados:
            tramites_citados.append(tramite_id)


def _armar_fuentes(conn, tramites_citados: list[str]) -> list[dict]:
    fuentes = []
    for tramite_id in tramites_citados:
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


def _armar_candidatos_ambiguos(conn, candidatos_buscados: dict[str, str]) -> list[dict]:
    candidatos_ambiguos = []
    for tramite_id in list(candidatos_buscados.keys())[:3]:
        snapshot = obtener_snapshot_vigente(conn, tramite_id)
        if snapshot is None:
            continue
        candidatos_ambiguos.append(
            {
                "tramite_id": tramite_id,
                "nombre_oficial": snapshot["nombre_oficial"],
                "descripcion": snapshot.get("descripcion", ""),
            }
        )
    return candidatos_ambiguos
