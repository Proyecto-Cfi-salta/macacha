from ingest.link_extractor import extract_official_links


def test_extracts_and_dedupes_urls_from_pasos_and_chunks():
    pasos = [
        "Ingresar a https://registrocivilsalta.gob.ar/",
        "Crear cuenta en https://registrocivilsalta.gob.ar/intro/login.php",
        "Pagar con Macroclick (QR, crédito o débito) o Mercado Pago.",
    ]
    chunks = [
        {
            "chunk_id": "RC-0001-CH-01",
            "texto": "texto",
            "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
        },
        {
            "chunk_id": "RC-0001-CH-02",
            "texto": "texto",
            "fuente": "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
        },
    ]

    resultado = extract_official_links(pasos, chunks)

    assert resultado == [
        "https://registrocivilsalta.gob.ar/",
        "https://registrocivilsalta.gob.ar/intro/login.php",
        "https://registrocivilsalta.gob.ar/oficial/tramites/actas-1",
    ]


def test_returns_empty_list_when_no_urls():
    assert extract_official_links(["Sin URLs acá."], []) == []
