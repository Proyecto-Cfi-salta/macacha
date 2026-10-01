from collections import Counter

from agent.admin import chats_repository

MAX_COMENTARIOS_RECIENTES = 20
SIN_TRAMITE = "Sin trámite"


def calcular_metricas(conn, organismo_id: int | None) -> dict:
    votos = _listar_votos(conn)
    citados = chats_repository.tramites_citados_por_sesion(
        conn, sorted({voto["session_id"] for voto in votos})
    )
    organismo_de_tramite = chats_repository.organismos_de_tramites(conn, citados)
    nombres = _nombres_de_organismos(conn)

    def organismos_de(session_id: str) -> set[int]:
        return {
            organismo_de_tramite[tramite_id]
            for tramite_id in citados.get(session_id, [])
            if tramite_id in organismo_de_tramite
        }

    if organismo_id is not None:
        votos = [voto for voto in votos if organismo_id in organismos_de(voto["session_id"])]

    positivos = sum(1 for voto in votos if voto["util"])
    negativos = len(votos) - positivos
    negativos_con_motivo = Counter(
        voto["motivo"] for voto in votos if not voto["util"] and voto["motivo"] is not None
    )

    por_dia: dict[str, dict] = {}
    for voto in votos:
        fecha = voto["creado_en"].date().isoformat()
        fila = por_dia.setdefault(fecha, {"fecha": fecha, "positivos": 0, "negativos": 0})
        fila["positivos" if voto["util"] else "negativos"] += 1

    por_organismo: dict[str, dict] = {}
    for voto in votos:
        if organismo_id is not None:
            claves = [nombres[organismo_id]]
        else:
            ids = organismos_de(voto["session_id"])
            claves = [nombres[i] for i in sorted(ids)] if ids else [SIN_TRAMITE]
        for clave in claves:
            fila = por_organismo.setdefault(clave, {"organismo": clave, "positivos": 0, "negativos": 0})
            fila["positivos" if voto["util"] else "negativos"] += 1

    comentarios = [
        {
            "session_id": voto["session_id"],
            "mensaje_id": voto["mensaje_id"],
            "motivo": voto["motivo"],
            "comentario": voto["comentario"],
            "creado_en": voto["creado_en"].isoformat(),
        }
        for voto in votos
        if not voto["util"] and voto["comentario"]
    ][:MAX_COMENTARIOS_RECIENTES]

    return {
        "total": len(votos),
        "positivos": positivos,
        "negativos": negativos,
        "porcentaje_util": round(100 * positivos / len(votos), 1) if votos else None,
        "motivos": [
            {"motivo": motivo, "cantidad": cantidad}
            for motivo, cantidad in sorted(negativos_con_motivo.items(), key=lambda par: (-par[1], par[0]))
        ],
        "sin_motivo": sum(1 for voto in votos if not voto["util"] and voto["motivo"] is None),
        "por_dia": sorted(por_dia.values(), key=lambda fila: fila["fecha"]),
        "comentarios_recientes": comentarios,
        "por_organismo": sorted(
            por_organismo.values(), key=lambda fila: (-(fila["positivos"] + fila["negativos"]), fila["organismo"])
        ),
    }


def _listar_votos(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT mensaje_id, session_id, util, motivo, comentario, created_at
            FROM feedback_respuestas
            ORDER BY created_at DESC, id DESC
            """
        )
        return [
            {
                "mensaje_id": str(mensaje_id),
                "session_id": str(session_id),
                "util": util,
                "motivo": motivo,
                "comentario": comentario,
                "creado_en": creado_en,
            }
            for mensaje_id, session_id, util, motivo, comentario, creado_en in cur.fetchall()
        ]


def _nombres_de_organismos(conn) -> dict[int, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, nombre FROM organismos")
        return {organismo_id: nombre for organismo_id, nombre in cur.fetchall()}
