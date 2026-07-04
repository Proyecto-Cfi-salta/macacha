import re

URL_PATTERN = re.compile(r"https?://[^\s)'\"]+")


def extract_official_links(pasos: list[str], chunks: list[dict]) -> list[str]:
    encontradas: list[str] = []

    for texto in pasos:
        encontradas.extend(URL_PATTERN.findall(texto))

    for chunk in chunks:
        fuente = chunk.get("fuente")
        if fuente:
            encontradas.append(fuente)

    vistas: set[str] = set()
    deduplicadas: list[str] = []
    for url in encontradas:
        url = url.rstrip(".,;")
        if url not in vistas:
            vistas.add(url)
            deduplicadas.append(url)

    return deduplicadas
