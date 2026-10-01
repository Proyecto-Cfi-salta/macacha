from typing import Literal

MOTIVOS = (
    "no_respondio",
    "info_incorrecta",
    "faltaba_info",
    "otro_tramite",
    "desactualizada",
    "poco_clara",
    "otro",
)

MotivoFeedback = Literal[MOTIVOS]  # type: ignore[valid-type]


def mensaje_votable(conn, session_id: str, mensaje_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM mensajes
            WHERE id = %s AND session_id = %s AND rol = 'assistant'
              AND tool_calls IS NULL AND contenido IS NOT NULL
            """,
            (mensaje_id, session_id),
        )
        return cur.fetchone() is not None


def guardar_voto(
    conn,
    session_id: str,
    mensaje_id: str,
    util: bool,
    motivo: str | None = None,
    comentario: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO feedback_respuestas (mensaje_id, session_id, util, motivo, comentario)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (mensaje_id) DO UPDATE SET
                util = EXCLUDED.util,
                motivo = CASE WHEN EXCLUDED.util THEN NULL
                              ELSE COALESCE(EXCLUDED.motivo, feedback_respuestas.motivo) END,
                comentario = CASE WHEN EXCLUDED.util THEN NULL
                                  ELSE COALESCE(EXCLUDED.comentario, feedback_respuestas.comentario) END,
                updated_at = now()
            """,
            (mensaje_id, session_id, util, motivo, comentario),
        )


def obtener_voto(conn, mensaje_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT util, motivo, comentario FROM feedback_respuestas WHERE mensaje_id = %s",
            (mensaje_id,),
        )
        fila = cur.fetchone()
    if fila is None:
        return None
    util, motivo, comentario = fila
    return {"util": util, "motivo": motivo, "comentario": comentario}
