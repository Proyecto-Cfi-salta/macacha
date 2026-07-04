_PREFIJOS_TIPO = [
    ("Requisitos para", "requisitos"),
    ("Pasos para", "pasos"),
    ("Costo, duración y modalidad de", "costo_modalidad"),
    ("Problemas frecuentes de", "problemas_frecuentes"),
]


def _inferir_tipo_chunk(texto: str) -> str:
    for prefijo, tipo in _PREFIJOS_TIPO:
        if texto.startswith(prefijo):
            return tipo
    return "descripcion"


def build_chunks(raw_tramite: dict, snapshot: dict) -> list[dict]:
    chunks: list[dict] = []

    for chunk_original in raw_tramite.get("chunks", []):
        chunks.append(
            {
                "tipo_chunk": _inferir_tipo_chunk(chunk_original["texto"]),
                "texto": chunk_original["texto"],
                "fuente_url": chunk_original.get("fuente"),
            }
        )

    for faq in snapshot["preguntas_frecuentes"]:
        chunks.append(
            {
                "tipo_chunk": "faq",
                "texto": f"{faq['pregunta']} {faq['respuesta']}",
                "fuente_url": None,
            }
        )

    if snapshot["enlaces_oficiales"]:
        chunks.append(
            {
                "tipo_chunk": "enlaces_oficiales",
                "texto": "Enlaces oficiales: " + ", ".join(snapshot["enlaces_oficiales"]),
                "fuente_url": snapshot["enlaces_oficiales"][0],
            }
        )

    return chunks
